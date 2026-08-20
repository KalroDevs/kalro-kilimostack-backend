import { useState } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import { AlertCircle } from "lucide-react";
import { authApi, AuthApiError } from "@/lib/authApi";
import { useAuthStore } from "@/lib/authStore";

export function Login() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const navigate = useNavigate();
  const location = useLocation();
  const setSession = useAuthStore((s) => s.setSession);
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated());

  const from = (location.state as { from?: string } | null)?.from ?? "/dashboard";

  const loginMutation = useMutation({
    mutationFn: () => authApi.login({ username, password }),
    onSuccess: (data) => {
      setSession(data.token, data.user);
      navigate(from, { replace: true });
    },
  });

  if (isAuthenticated) {
    return <Navigate to="/dashboard" replace />;
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-canvas px-4">
      <div className="w-full max-w-sm">
        <Link to="/" className="field-label mb-1 block">
          KilimoSTACK · OpenAgriNet
        </Link>
        <h1 className="font-display text-2xl font-semibold text-ink">Log in</h1>
        <p className="mt-1 text-sm text-ink/55">Screen content, or ask the advisory AI.</p>

        <form
          className="card mt-6 space-y-4 p-6"
          onSubmit={(e) => {
            e.preventDefault();
            loginMutation.mutate();
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
          </label>
          <label className="block">
            <span className="field-label">Password</span>
            <input
              className="input mt-1.5"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              required
            />
          </label>

          {loginMutation.isError && (
            <p className="flex items-start gap-1.5 text-sm text-rust">
              <AlertCircle className="mt-0.5 h-4 w-4 flex-shrink-0" />
              {loginMutation.error instanceof AuthApiError
                ? loginMutation.error.message
                : "Couldn't reach the server. Check the API URL under Settings."}
            </p>
          )}

          <button type="submit" className="btn-primary w-full" disabled={loginMutation.isPending}>
            {loginMutation.isPending ? "Logging in…" : "Log in"}
          </button>
        </form>

        <p className="mt-4 text-center text-sm text-ink/55">
          Don't have an account?{" "}
          <Link to="/register" className="font-medium text-herbarium hover:underline">
            Register
          </Link>
        </p>
      </div>
    </div>
  );
}
