import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import clsx from "clsx";
import { LayoutGrid, Library, LogOut, MessageCircleQuestion, Settings as SettingsIcon, Upload } from "lucide-react";
import { authApi } from "@/lib/authApi";
import { useAuthStore } from "@/lib/authStore";

const navItems = [
  { to: "/dashboard", label: "Overview", icon: LayoutGrid, end: true },
  { to: "/resources", label: "Corpus Ledger", icon: Library, end: false },
  { to: "/import", label: "Import", icon: Upload, end: false },
  { to: "/advisory", label: "Ask the Advisory AI", icon: MessageCircleQuestion, end: false },
  { to: "/settings", label: "Settings", icon: SettingsIcon, end: false },
];

export function Layout() {
  const navigate = useNavigate();
  const { user, token, clearSession } = useAuthStore();

  const logoutMutation = useMutation({
    mutationFn: () => authApi.logout(token!),
    onSettled: () => {
      clearSession();
      navigate("/login", { replace: true });
    },
  });

  return (
    <div className="flex min-h-screen">
      <aside className="flex w-64 flex-shrink-0 flex-col border-r border-wire bg-paper">
        <div className="border-b border-wire px-5 py-5">
          <p className="field-label">KilimoSTACK · OAN</p>
          <h1 className="mt-1 font-display text-xl font-semibold leading-tight text-ink">
            KALRO Advisory Corpus
          </h1>
        </div>

        <nav className="flex-1 space-y-0.5 px-3 py-4">
          {navItems.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                clsx(
                  "flex items-center gap-2.5 rounded-[3px] px-3 py-2 text-sm font-medium transition-colors",
                  isActive
                    ? "bg-herbarium text-paper"
                    : "text-ink/65 hover:bg-canvas2 hover:text-ink"
                )
              }
            >
              <Icon className="h-4 w-4 flex-shrink-0" />
              {label}
            </NavLink>
          ))}
        </nav>

        <div className="border-t border-wire px-4 py-4">
          {user && (
            <div className="mb-3">
              <p className="truncate text-sm font-medium text-ink">{user.username}</p>
              <p className="mt-0.5 text-xs text-ink/45">
                {user.provider_memberships.length > 0
                  ? user.provider_memberships.map((m) => m.provider_name).join(", ")
                  : "No provider access yet"}
              </p>
            </div>
          )}
          <button
            className="flex w-full items-center gap-2 rounded-[3px] px-1 py-1.5 text-xs font-medium text-ink/50 hover:text-rust"
            onClick={() => logoutMutation.mutate()}
            disabled={logoutMutation.isPending}
          >
            <LogOut className="h-3.5 w-3.5" />
            {logoutMutation.isPending ? "Logging out…" : "Log out"}
          </button>
        </div>
      </aside>

      <main className="min-w-0 flex-1">
        <Outlet />
      </main>
    </div>
  );
}
