import { useState } from "react";
import { useAuth } from "./hooks/useAuth";
import { useInvoices } from "./hooks/useInvoices";
import { LoginScreen } from "./components/LoginScreen";
import { InvoiceDetail } from "./components/InvoiceDetail";
import { InvoiceTable } from "./components/InvoiceTable";

export default function App() {
  const {token, signIn, signOut} = useAuth();
  const [authError, setAuthError] = useState("");
  const invoices = useInvoices(token);
  if (!token) return <LoginScreen error={authError} onSignIn={signIn} onError={setAuthError} />;
  return <div className="app-shell"><header><div className="brand"><span className="brand-mark small">L</span><div><strong>Ledgerly</strong><small>Invoice workspace</small></div></div><button className="ghost" onClick={signOut}>Sign out</button></header><main className="workspace"><section className="hero-row"><div><span className="eyebrow">Overview</span><h1>Invoices, without the busywork.</h1><p>Extract structured data and review it before it moves downstream.</p></div><label className={invoices.busy ? "upload disabled" : "upload"}><input type="file" accept="application/pdf" disabled={invoices.busy} onChange={event => void invoices.upload(event.target.files?.[0])}/><span>{invoices.busy ? "Processing…" : "Upload invoice"}</span><small>PDF · up to 10 MB</small></label></section>{invoices.error && <div className="error banner" role="alert">{invoices.error}<button onClick={() => invoices.setError("")}>Dismiss</button></div>}<section className="content-grid"><div className="invoice-list"><div className="section-title"><div><span className="eyebrow">Recent activity</span><h2>Processed invoices</h2></div><button className="ghost" onClick={() => void invoices.refresh()} disabled={invoices.busy}>Refresh</button></div>{invoices.invoices.length === 0 && !invoices.busy ? <div className="empty"><span>⌁</span><h3>No invoices yet</h3><p>Upload your first PDF to see extracted fields here.</p></div> : <InvoiceTable invoices={invoices.invoices} selectedId={invoices.selected?.id} onSelect={invoices.setSelectedId}/>}</div>{invoices.selected ? <InvoiceDetail invoice={invoices.selected}/> : <aside className="detail-panel placeholder"><p>Select an invoice to inspect its extracted data.</p></aside>}</section></main></div>;
}
