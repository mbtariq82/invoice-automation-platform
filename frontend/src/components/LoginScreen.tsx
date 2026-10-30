import { GoogleLogin } from "@react-oauth/google";

export function LoginScreen({error, onSignIn, onError}: {error: string; onSignIn: (token: string) => void; onError: (message: string) => void}) {
  return <main className="login-shell"><section className="login-card"><div className="brand-mark">L</div><span className="eyebrow">Invoice automation workspace</span><h1>Turn invoices into reliable data.</h1><p>Upload a PDF, validate extracted totals and keep every processed invoice in one calm workspace.</p><GoogleLogin onSuccess={({credential}) => credential && onSignIn(credential)} onError={() => onError("Google sign-in was not completed")} useOneTap />{error && <p className="error" role="alert">{error}</p>}<small>Access is restricted to members configured for this environment.</small></section><div className="login-art" aria-hidden="true"><div className="paper"><i/><i/><i/><b/></div></div></main>;
}
