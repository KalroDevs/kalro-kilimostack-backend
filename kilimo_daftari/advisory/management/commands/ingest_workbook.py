from __future__ import annotations
import re
from collections import OrderedDict
from datetime import date, datetime
from pathlib import Path

import openpyxl
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from advisory.models import AdvisoryResource, ContentSection


IGNORED_SHEETS = {
    "Instructions",
    "Summary",
    "README",
}


_MULTI_SPLIT = re.compile(r"\s*;\s*|\r?\n")

# Used to normalise join keys: 'CROP-007' / 'CROP 007' / 'crop007' → 'CROP007'.
_NORMALISE_KEY = re.compile(r"[^A-Za-z0-9]")



def clean(value) -> str:
    """Return a trimmed string, '' for None."""
    if value is None:
        return ""
    return str(value).strip()


def split_list(value) -> list[str]:
    """Split a cell on ';' or newlines; drop blanks."""
    s = clean(value)
    if not s:
        return []
    return [p.strip() for p in _MULTI_SPLIT.split(s) if p.strip()]


def split_tags(value) -> list[str]:
    """Split a comma-separated tags cell; drop blanks."""
    s = clean(value)
    if not s:
        return []
    return [t.strip() for t in s.split(",") if t.strip()]


def parse_date(value):
    """Accept date objects or strings; return a date or None."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    s = str(value).strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def normalise_key(s: str) -> str:
    """'CROP-007' / 'CROP 007' / 'crop007' → 'CROP007'."""
    return _NORMALISE_KEY.sub("", s or "").upper()


def find_header_row(ws, needle: str, max_scan: int = 20) -> int | None:
    """Return the 1-based row index where a cell equals ``needle`` (case-insensitive)."""
    needle = needle.strip().lower()
    for r in range(1, min(ws.max_row, max_scan) + 1):
        for c in range(1, ws.max_column + 1):
            if clean(ws.cell(row=r, column=c).value).lower() == needle:
                return r
    return None


def header_map(ws, header_row: int) -> dict[str, int]:
    """Map lowercase header name → column index for a given header row."""
    mapping = {}
    for c in range(1, ws.max_column + 1):
        h = clean(ws.cell(row=header_row, column=c).value)
        if h:
            mapping[h.lower().replace("\n", " ")] = c
    return mapping


def resolve_header(cols: dict[str, int], *candidates: str) -> int | None:
    """Return the column index whose header matches any candidate (substring, case-insensitive)."""
    for candidate in candidates:
        c = candidate.lower()
        for header, idx in cols.items():
            if c in header:
                return idx
    return None


# ---------------------------------------------------------------------------
# Sheet classification
# ---------------------------------------------------------------------------
def classify_sheet(ws) -> str:
    """
    Return one of:
        "inventory"   -- header row contains ID + Content Title
        "section"     -- header row contains Section Header + Content Summary + Pages
        "ignore"      -- neither

    Only header cells are inspected, so a stray data cell containing the
    word "ID" will not fool the classifier.
    """
    if ws.title in IGNORED_SHEETS:
        return "ignore"

    for r in range(1, min(ws.max_row, 20) + 1):
        cells = {
            clean(ws.cell(row=r, column=c).value).lower()
            for c in range(1, ws.max_column + 1)
        }
        # Section check first because it's the more specific signature.
        if {"section header", "content summary", "pages"} <= cells and "content title" not in cells:
            return "section"
        if {"id", "content title"} <= cells:
            return "inventory"
    return "ignore"


# ---------------------------------------------------------------------------
# Sheet parsers
# ---------------------------------------------------------------------------
def parse_inventory_sheet(ws, group: str) -> list[dict]:
    """
    Parse an inventory sheet into a list of AdvisoryResource-shaped dicts.
    Columns are located by header name, not index.
    """
    header_row = find_header_row(ws, "ID")
    if header_row is None:
        return []

    cols = header_map(ws, header_row)

    col_id      = resolve_header(cols, "id")
    col_title   = resolve_header(cols, "content title")
    col_pub     = resolve_header(cols, "publication id", "source link")
    col_inst    = resolve_header(cols, "institution")
    col_pubdate = resolve_header(cols, "publish date")
    col_vc      = resolve_header(cols, "value chain", "commodity")
    col_dom     = resolve_header(cols, "advisory domain", "topic")
    col_type    = resolve_header(cols, "content type")
    col_fmt     = resolve_header(cols, "format")
    col_psys    = resolve_header(cols, "production system")
    col_users   = resolve_header(cols, "target users")
    col_aez     = resolve_header(cols, "country", "aez")
    col_review  = resolve_header(cols, "last reviewed", "currency check")
    col_curr    = resolve_header(cols, "currency status")
    col_acc     = resolve_header(cols, "scientific accuracy")
    col_valid   = resolve_header(cols, "validation status")
    col_risk    = resolve_header(cols, "risk level")
    col_flag    = resolve_header(cols, "quality flag")
    col_notes   = resolve_header(cols, "screening notes", "escalation")

    if not col_id or not col_title:
        raise CommandError(
            f"Sheet '{ws.title}': could not locate the ID / Content Title columns."
        )

    rows = []
    for r in range(header_row + 1, ws.max_row + 1):
        rid   = clean(ws.cell(row=r, column=col_id).value)
        title = clean(ws.cell(row=r, column=col_title).value)
        if not rid or not title:
            continue
        if rid.upper().endswith("-EX"):
            # Worked-example row (CROP-EX / LVS-EX); do not import.
            continue

                # Column L ("Country / AEZ") goes into the geographic_applicability
        # JSON blob because the model has no flat country_aez field.
        country_aez_raw = clean(ws.cell(row=r, column=col_aez).value) if col_aez else ""
        geographic_applicability = {}
        if country_aez_raw:
            # The workbook uses "Kenya - Arid & Semi-Arid Lands" style strings.
            # Split on the first hyphen into country + zone; keep the raw text
            # in ``notes`` so nothing is lost.
            if "-" in country_aez_raw:
                country, _, zone = country_aez_raw.partition("-")
                geographic_applicability = {
                    "country": country.strip(),
                    "agro_ecological_zones": [zone.strip()] if zone.strip() else [],
                    "notes": country_aez_raw,
                }
            else:
                geographic_applicability = {
                    "country": country_aez_raw,
                    "agro_ecological_zones": [],
                    "notes": "",
                }

        rows.append({
            "resource_id":               rid,
            "title":                     title,
            "publication_id":            clean(ws.cell(row=r, column=col_pub).value) if col_pub else "",
            "institution":               (clean(ws.cell(row=r, column=col_inst).value) if col_inst else "")
                                         or "Kenya Agricultural and Livestock Research Organization",
            "publish_date":              clean(ws.cell(row=r, column=col_pubdate).value) if col_pubdate else "",
            "value_chain":               clean(ws.cell(row=r, column=col_vc).value) if col_vc else "",
            "advisory_domain":           split_list(ws.cell(row=r, column=col_dom).value) if col_dom else [],
            "content_type":              clean(ws.cell(row=r, column=col_type).value) if col_type else "",
            "production_system":         split_list(ws.cell(row=r, column=col_psys).value) if col_psys else [],
            "target_users":              split_list(ws.cell(row=r, column=col_users).value) if col_users else [],
            "geographic_applicability":  geographic_applicability,
            "review_date":               parse_date(ws.cell(row=r, column=col_review).value) if col_review else None,
            "currency_status":           clean(ws.cell(row=r, column=col_curr).value) if col_curr else "",
            "scientific_accuracy_check": clean(ws.cell(row=r, column=col_acc).value) if col_acc else "",
            "validation_status":         clean(ws.cell(row=r, column=col_valid).value) if col_valid else "",
            "risk_level":                clean(ws.cell(row=r, column=col_risk).value) if col_risk else "",
            "quality_flag":              clean(ws.cell(row=r, column=col_flag).value) if col_flag else "",
            "screening_notes":           clean(ws.cell(row=r, column=col_notes).value) if col_notes else "",
            "group":                     group,
        })
    return rows


def parse_section_sheet(ws, sheet_name: str) -> list[dict]:
    """
    Parse a section sheet into a list of ContentSection-shaped dicts.
    Expected columns: #, Section Header, Content Summary, Pages,
                      Content Warnings, Content Tags
    """
    header_row = find_header_row(ws, "Section Header")
    if header_row is None:
        return []

    cols = header_map(ws, header_row)
    col_num     = resolve_header(cols, "#")
    col_header  = resolve_header(cols, "section header")
    col_summary = resolve_header(cols, "content summary")
    col_pages   = resolve_header(cols, "pages")
    col_warn    = resolve_header(cols, "content warnings")
    col_tags    = resolve_header(cols, "content tags")

    if not (col_num and col_header and col_summary and col_pages):
        raise CommandError(
            f"Sheet '{sheet_name}': missing one of #, Section Header, "
            f"Content Summary, or Pages."
        )

    sections = []
    for r in range(header_row + 1, ws.max_row + 1):
        raw_num = ws.cell(row=r, column=col_num).value
        if raw_num in (None, ""):
            continue
        try:
            order = int(float(raw_num))
        except (TypeError, ValueError):
            continue

        header  = clean(ws.cell(row=r, column=col_header).value)
        summary = clean(ws.cell(row=r, column=col_summary).value)
        pages   = clean(ws.cell(row=r, column=col_pages).value)
        warn    = clean(ws.cell(row=r, column=col_warn).value) if col_warn else ""
        tags    = clean(ws.cell(row=r, column=col_tags).value) if col_tags else ""

        if not (header or summary):
            continue

        sections.append({
            "reading_order":    order,
            "content_header":   header,
            "content_text":     summary,
            "pages_reference":  pages,
            "content_warnings": split_list(warn),
            "content_tags":     split_tags(tags),
            "value_chain":      sheet_name,
        })
    return sections


# ---------------------------------------------------------------------------
# Per-sheet statistics (used for the final report)
# ---------------------------------------------------------------------------
class SheetReport:
    __slots__ = (
        "workbook", "sheet", "role", "group", "rows_parsed",
        "resources_created", "resources_updated",
        "sections_created", "sections_updated", "sections_skipped",
        "unresolved_parents",
    )

    def __init__(self, workbook: str, sheet: str, role: str, group: str = ""):
        self.workbook = workbook
        self.sheet = sheet
        self.role = role
        self.group = group
        self.rows_parsed = 0
        self.resources_created = 0
        self.resources_updated = 0
        self.sections_created = 0
        self.sections_updated = 0
        self.sections_skipped = 0
        self.unresolved_parents: dict[str, int] = {}


# ---------------------------------------------------------------------------
# Command
# ---------------------------------------------------------------------------
class Command(BaseCommand):
    help = (
        "Ingest one or more Screen & Classify Excel workbooks into the "
        "database (and optionally ChromaDB)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "workbooks",
            nargs="+",
            help="One or more paths to Screen & Classify .xlsx workbooks.",
        )
        parser.add_argument(
            "--only-sheet",
            action="append",
            default=None,
            help="Restrict ingestion to the given sheet name(s). May be repeated.",
        )
        parser.add_argument(
            "--section-sheet",
            action="append",
            default=None,
            metavar="SHEET",
            help="Force-classify a sheet as a section sheet. May be repeated.",
        )
        parser.add_argument(
            "--inventory-sheet",
            action="append",
            default=None,
            metavar="SHEET:group",
            help=(
                "Force-classify a sheet as an inventory sheet and set its "
                "group label, e.g. --inventory-sheet 'Crops 2026:crops'. "
                "May be repeated."
            ),
        )
        parser.add_argument(
            "--no-chroma",
            action="store_true",
            help="Skip the ChromaDB push entirely.",
        )
        parser.add_argument(
            "--chroma-host", default="localhost",
            help="ChromaDB host (default: localhost).",
        )
        parser.add_argument(
            "--chroma-port", type=int, default=8000,
            help="ChromaDB port (default: 8000).",
        )
        parser.add_argument(
            "--chroma-collection", default="advisory_sections",
            help="ChromaDB collection name (default: advisory_sections).",
        )
        parser.add_argument(
            "--embedding-model", default="all-MiniLM-L6-v2",
            help="Sentence-transformer model used by Chroma (default: all-MiniLM-L6-v2).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Parse and report, but do not write to the database.",
        )
        parser.add_argument(
            "--report",
            action="store_true",
            help="Print a detailed per-sheet report at the end.",
        )

    # -- entry point -------------------------------------------------------
    def handle(self, *args, **options):
        only = set(options["only_sheet"] or [])
        dry_run = options["dry_run"]
        show_report = options["report"]

        # Parse override flags -------------------------------------------
        inventory_overrides: dict[str, str] = {}
        for entry in options["inventory_sheet"] or []:
            if ":" not in entry:
                raise CommandError(
                    f"--inventory-sheet expects 'SHEET:group', got: {entry}"
                )
            sheet, group = entry.split(":", 1)
            inventory_overrides[sheet.strip()] = group.strip()

        forced_sections = set(options["section_sheet"] or [])

        # ------------------------------------------------------------------
        # Phase 1: open every workbook, classify every sheet, parse rows.
        # ------------------------------------------------------------------
        self.stdout.write(self.style.MIGRATE_HEADING(
            f"Loading {len(options['workbooks'])} workbook(s)"
        ))

        # (workbook_path, group_label_if_inventory, SheetReport, rows)
        parsed: list[tuple[Path, str, SheetReport, list[dict]]] = []
        all_inventory_rows: list[dict] = []
        all_section_rows: list[dict] = []

        reports: "OrderedDict[tuple[str, str], SheetReport]" = OrderedDict()

        for raw_path in options["workbooks"]:
            wb_path = Path(raw_path).expanduser().resolve()
            if not wb_path.is_file():
                raise CommandError(f"Workbook not found: {wb_path}")

            self.stdout.write(f"  • {wb_path.name}")
            wb = openpyxl.load_workbook(str(wb_path), data_only=True, read_only=False)

            for sheet_name in wb.sheetnames:
                if only and sheet_name not in only:
                    continue

                ws = wb[sheet_name]

                if sheet_name in inventory_overrides:
                    role = "inventory"
                    group = inventory_overrides[sheet_name]
                elif sheet_name in forced_sections:
                    role = "section"
                    group = ""
                else:
                    role = classify_sheet(ws)
                    group = ""

                if role == "ignore":
                    self.stdout.write(f"      · Skipping '{sheet_name}' (ignored).")
                    continue

                if role == "inventory":
                    if not group:
                        # Fall back to a slug of the sheet name.
                        group = re.sub(r"[^a-z0-9]+", "_", sheet_name.lower()).strip("_")
                    rows = parse_inventory_sheet(ws, group)
                    report = SheetReport(wb_path.name, sheet_name, "inventory", group)
                    report.rows_parsed = len(rows)
                    reports[(wb_path.name, sheet_name)] = report
                    parsed.append((wb_path, group, report, rows))
                    all_inventory_rows.extend((group, r) for r in rows)
                    self.stdout.write(
                        f"      + inventory '{sheet_name}' → group '{group}': "
                        f"{len(rows)} rows"
                    )

                elif role == "section":
                    rows = parse_section_sheet(ws, sheet_name)
                    report = SheetReport(wb_path.name, sheet_name, "section")
                    report.rows_parsed = len(rows)
                    reports[(wb_path.name, sheet_name)] = report
                    parsed.append((wb_path, "", report, rows))
                    all_section_rows.extend((wb_path.name, sheet_name, r) for r in rows)
                    self.stdout.write(
                        f"      + section   '{sheet_name}': {len(rows)} rows"
                    )

        self.stdout.write(self.style.SUCCESS(
            f"  → {len(all_inventory_rows)} inventory rows across all workbooks, "
            f"{len(all_section_rows)} section rows"
        ))

        if dry_run:
            self._print_dry_run(all_inventory_rows, all_section_rows, reports, show_report)
            return

        # ------------------------------------------------------------------
        # Phase 2: upsert AdvisoryResource rows.
        # ------------------------------------------------------------------
        with transaction.atomic():
            created_rs, updated_rs = self._upsert_resources(all_inventory_rows, reports)

        self.stdout.write(self.style.SUCCESS(
            f"AdvisoryResource: +{created_rs} created, ~{updated_rs} updated "
            f"({AdvisoryResource.objects.count()} total)"
        ))

        # ------------------------------------------------------------------
        # Phase 3: resolve parents & upsert ContentSection rows.
        # ------------------------------------------------------------------
        with transaction.atomic():
            created_cs, updated_cs, skipped_cs = self._upsert_sections(
                all_section_rows, reports
            )

        self.stdout.write(self.style.SUCCESS(
            f"ContentSection : +{created_cs} created, ~{updated_cs} updated, "
            f"{skipped_cs} skipped ({ContentSection.objects.count()} total)"
        ))

        # ------------------------------------------------------------------
        # Phase 4: optional report.
        # ------------------------------------------------------------------
        if show_report:
            self._print_report(reports)

        # ------------------------------------------------------------------
        # Phase 5: push to ChromaDB.
        # ------------------------------------------------------------------
        if options["no_chroma"]:
            self.stdout.write("ChromaDB push skipped (--no-chroma).")
            return

        self._push_to_chroma(
            host=options["chroma_host"],
            port=options["chroma_port"],
            collection_name=options["chroma_collection"],
            model_name=options["embedding_model"],
        )

    # -- DB writers --------------------------------------------------------
    def _upsert_resources(
        self,
        inventory_rows: list[tuple[str, dict]],
        reports: "OrderedDict[tuple[str, str], SheetReport]",
    ) -> tuple[int, int]:
        """
        ``inventory_rows`` is a list of ``(group, row_dict)`` tuples.
        Returns (created_count, updated_count).
        """
        created = updated = 0
        # Map (workbook, sheet) back to a report so we can tally per-sheet.
        # Build a lookup from group name → report for convenience.
        by_group: dict[str, SheetReport] = {}
        for rep in reports.values():
            if rep.role == "inventory":
                by_group[rep.group] = rep

        for group, row in inventory_rows:
            data = dict(row)
            rid = data.pop("resource_id")
            _, was_created = AdvisoryResource.objects.update_or_create(
                resource_id=rid,
                defaults=data,
            )
            if was_created:
                created += 1
                rep = by_group.get(group)
                if rep:
                    rep.resources_created += 1
            else:
                updated += 1
                rep = by_group.get(group)
                if rep:
                    rep.resources_updated += 1
        return created, updated

    def _upsert_sections(
        self,
        section_rows: list[tuple[str, str, dict]],
        reports: "OrderedDict[tuple[str, str], SheetReport]",
    ) -> tuple[int, int, int]:
        """
        ``section_rows`` is a list of ``(workbook_name, sheet_name, row_dict)``.
        Returns (created, updated, skipped).
        """
        lookup = {r.resource_id: r for r in AdvisoryResource.objects.all()}
        fallback = {normalise_key(r.resource_id): r for r in lookup.values()}

        created = updated = skipped = 0

        for workbook_name, sheet_name, row in section_rows:
            rep = reports.get((workbook_name, sheet_name))

            parent_id = row["pages_reference"]
            parent = lookup.get(parent_id) or fallback.get(normalise_key(parent_id))
            if parent is None:
                skipped += 1
                if rep is not None:
                    rep.sections_skipped += 1
                    rep.unresolved_parents[parent_id] = (
                        rep.unresolved_parents.get(parent_id, 0) + 1
                    )
                continue

            content_id = f"{parent.resource_id}-S{row['reading_order']:04d}"
            _, was_created = ContentSection.objects.update_or_create(
                content_id=content_id,
                defaults={
                    "resource":         parent,
                    "reading_order":    row["reading_order"],
                    "content_header":   row["content_header"],
                    "content_text":     row["content_text"],
                    "pages_reference":  row["pages_reference"],
                    "content_warnings": row["content_warnings"],
                    "content_tags":     row["content_tags"],
                    "value_chain":      row["value_chain"],
                },
            )
            if was_created:
                created += 1
                if rep:
                    rep.sections_created += 1
            else:
                updated += 1
                if rep:
                    rep.sections_updated += 1

        return created, updated, skipped

    # -- reporting ---------------------------------------------------------
    def _print_dry_run(
        self,
        inventory_rows: list[tuple[str, dict]],
        section_rows: list[tuple[str, str, dict]],
        reports: "OrderedDict[tuple[str, str], SheetReport]",
        show_report: bool,
    ) -> None:
        self.stdout.write(self.style.MIGRATE_HEADING("Dry run — no DB writes"))

        by_group: dict[str, int] = {}
        for group, _ in inventory_rows:
            by_group[group] = by_group.get(group, 0) + 1
        for group, count in by_group.items():
            self.stdout.write(f"  inventory group '{group}': {count} rows")

        by_sheet: dict[str, int] = {}
        for _, sheet_name, _ in section_rows:
            by_sheet[sheet_name] = by_sheet.get(sheet_name, 0) + 1
        for sheet_name, count in by_sheet.items():
            self.stdout.write(f"  section sheet  '{sheet_name}': {count} rows")

        if show_report:
            self._print_report(reports)

    def _print_report(
        self,
        reports: "OrderedDict[tuple[str, str], SheetReport]",
    ) -> None:
        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("Per-sheet report"))

        # Column widths chosen to fit the widest reasonable workbook name.
        fmt = (
            "  {wb:<28} {sheet:<22} {role:<10} "
            "{parsed:>6} {rc:>5} {ru:>5} {sc:>5} {su:>5} {sk:>5}"
        )
        self.stdout.write(fmt.format(
            wb="Workbook", sheet="Sheet", role="Role",
            parsed="Parsed", rc="+Res", ru="~Res", sc="+Sec", su="~Sec", sk="Skip",
        ))
        self.stdout.write("  " + "-" * 100)

        for (wb_name, sheet_name), rep in reports.items():
            self.stdout.write(fmt.format(
                wb=wb_name[:28],
                sheet=sheet_name[:22],
                role=rep.role,
                parsed=rep.rows_parsed,
                rc=rep.resources_created,
                ru=rep.resources_updated,
                sc=rep.sections_created,
                su=rep.sections_updated,
                sk=rep.sections_skipped,
            ))
            for parent_id, count in rep.unresolved_parents.items():
                self.stdout.write(
                    self.style.WARNING(
                        f"      ! unresolved parent '{parent_id}' × {count}"
                    )
                )

    # -- ChromaDB ----------------------------------------------------------
    def _push_to_chroma(
        self, host: str, port: int, collection_name: str, model_name: str
    ) -> None:
        try:
            import chromadb
            from chromadb.utils import embedding_functions
        except ImportError as exc:
            raise CommandError(
                "chromadb is not installed. Install it or re-run with --no-chroma."
            ) from exc

        self.stdout.write(self.style.MIGRATE_HEADING("Connecting to ChromaDB"))
        client = chromadb.HttpClient(host=host, port=port)
        embedder = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=model_name
        )
        collection = client.get_or_create_collection(
            name=collection_name,
            embedding_function=embedder,
            metadata={"hnsw:space": "cosine"},
        )

        qs = ContentSection.objects.select_related("resource").all()
        total = qs.count()
        self.stdout.write(f"  Embedding {total} sections with '{model_name}'…")

        BATCH = 100
        ids: list[str] = []
        docs: list[str] = []
        metas: list[dict] = []
        pushed = 0

        def flush():
            nonlocal pushed
            if not ids:
                return
            collection.upsert(ids=ids, documents=docs, metadatas=metas)
            pushed += len(ids)
            ids.clear()
            docs.clear()
            metas.clear()

        for sec in qs.iterator(chunk_size=BATCH):
            ids.append(sec.content_id)
            docs.append(f"{sec.content_header}\n\n{sec.content_text}".strip())
            metas.append({
                "content_id":     sec.content_id,
                "resource_id":    sec.resource.resource_id,
                "title":          sec.resource.title,
                "value_chain":    sec.value_chain or sec.resource.value_chain,
                "content_header": sec.content_header,
                "risk_level":     sec.resource.risk_level,
                "quality_flag":   sec.resource.quality_flag,
                "has_warnings":   bool(sec.content_warnings),
                "content_tags":   ", ".join(sec.content_tags),
                "group":          sec.resource.group or "",
            })
            if len(ids) >= BATCH:
                flush()

        flush()
        self.stdout.write(self.style.SUCCESS(
            f"ChromaDB collection '{collection_name}' holds "
            f"{collection.count()} documents ({pushed} pushed this run)."
        ))