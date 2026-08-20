import { useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import { AlertCircle, Info } from "lucide-react";
import { authApi, AuthApiError } from "@/lib/authApi";
import { useAuthStore } from "@/lib/authStore";

export function Register() {
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const navigate = useNavigate();
  const setSession = useAuthStore((s) => s.setSession);
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated());

  const registerMutation = useMutation({
    mutationFn: () => authApi.register({ username, email, password }),
    onSuccess: (data) => {
      setSession(data.token, data.user);
      navigate("/dashboard", { replace: true });
    },
  });

  const fieldErrors = registerMutation.error instanceof AuthApiError ? registerMutation.error.fieldErrors : null;

  if (isAuthenticated) {
    return <Navigate to="/dashboard" replace />;
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-canvas px-4">
      <div className="w-full max-w-sm">
        <Link to="/" className="field-label mb-1 block">
          KilimoSTACK · OpenAgriNet
        </Link>
        <h1 className="font-display text-2xl font-semibold text-ink">Create an account</h1>
        <p className="mt-1 text-sm text-ink/55">You can browse right away; screening access is granted by an admin.</p>

        <form
          className="card mt-6 space-y-4 p-6"
          onSubmit={(e) => {
            e.preventDefault();
            registerMutation.mutate();
          }}
        >
          <label className="block">
            <span className="field-label">Username</span>
            <input
              className="input mt-1.5"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoComplete="username"
              autoFocus
              required
            />
            {fieldErrors?.username && <p className="mt-1 text-xs text-rust">{fieldErrors.username[0]}</p>}
          </label>

          <label className="block">
            <span className="field-label">Email (optional)</span>
            <input
              className="input mt-1.5"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="email"
            />
            {fieldErrors?.email && <p className="mt-1 text-xs text-rust">{fieldErrors.email[0]}</p>}
          </label>

          <label className="block">
            <span className="field-label">Password</span>
            <input
              className="input mt-1.5"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="new-password"
              required
            />
            {fieldErrors?.password && <p className="mt-1 text-xs text-rust">{fieldErrors.password[0]}</p>}
          </label>

          {registerMutation.isError && !fieldErrors && (
            <p className="flex items-start gap-1.5 text-sm text-rust">
              <AlertCircle className="mt-0.5 h-4 w-4 flex-shrink-0" />
              {registerMutation.error instanceof AuthApiError
                ? registerMutation.error.message
                : "Couldn't reach the server. Check the API URL under Settings."}
            </p>
          )}

          <button type="submit" className="btn-primary w-full" disabled={registerMutation.isPending}>
            {registerMutation.isPending ? "Creating account…" : "Create account"}
          </button>

          <p className="flex items-start gap-1.5 rounded-[3px] border border-wire bg-canvas/60 px-2.5 py-2 text-xs text-ink/55">
            <Info className="mt-0.5 h-3.5 w-3.5 flex-shrink-0" />
            New accounts can browse certified content immediately. Screening/certifying on behalf of a
            provider requires an admin to link your account to that provider.
          </p>
        </form>

        <p className="mt-4 text-center text-sm text-ink/55">
          Already have an account?{" "}
          <Link to="/login" className="font-medium text-herbarium hover:underline">
            Log in
          </Link>
        </p>
      </div>
    </div>
  );
}
