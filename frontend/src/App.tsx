import { GoogleLogin, googleLogout } from "@react-oauth/google";
import { useCallback, useEffect, useMemo, useState } from "react";
import { extractInvoice, InvoiceRecord, listInvoices } from "./api";

const TOKEN_KEY = "invoice-google-id-token";

function money(value: string, currency: string) {
  const amount = Number(value);
  if (!Number.isFinite(amount)) return `${currency} ${value}`;
  try {
    return new Intl.NumberFormat(undefined, {style: "currency", currency}).format(amount);
  } catch {
    return `${currency} ${amount.toFixed(2)}`;
  }
}

function InvoicePanel({invoice}: {invoice: InvoiceRecord}) {
  return <aside className="detail-panel" aria-label="Invoice details">
    <div className="detail-heading">
      <div><span className="eyebrow">Invoice detail</span><h2>{invoice.vendor_name}</h2></div>
      <span className={invoice.totals_check.is_consistent ? "status valid" : "status warning"}>
        {invoice.totals_check.is_consistent ? "Totals verified" : "Review totals"}
      </span>
    </div>
    <dl className="detail-grid">
      <div><dt>Invoice number</dt><dd>{invoice.invoice_number}</dd></div>
      <div><dt>Invoice date</dt><dd>{invoice.invoice_date}</dd></div>
      <div><dt>Source file</dt><dd>{invoice.source_filename ?? "—"}</dd></div>
      <div><dt>Processed</dt><dd>{new Date(invoice.created_at).toLocaleString()}</dd></div>
    </dl>
    <div className="amount-stack">
      <div><span>Subtotal</span><strong>{money(invoice.subtotal, invoice.currency)}</strong></div>
      <div><span>Tax</span><strong>{money(invoice.tax, invoice.currency)}</strong></div>
      <div className="total"><span>Total</span><strong>{money(invoice.total, invoice.currency)}</strong></div>
    </div>
  </aside>;
}

export default function App() {
  const [token, setToken] = useState(() => sessionStorage.getItem(TOKEN_KEY) ?? "");
  const [invoices, setInvoices] = useState<InvoiceRecord[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const selected = useMemo(
    () => invoices.find(invoice => invoice.id === selectedId) ?? invoices[0],
    [invoices, selectedId]
  );

  const refresh = useCallback(async () => {
    if (!token) return;
    setBusy(true);
    setError("");
    try {
      const records = await listInvoices(token);
      setInvoices(records);
      setSelectedId(current => current ?? records[0]?.id ?? null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not load invoices");
    } finally {
      setBusy(false);
    }
  }, [token]);

  useEffect(() => { void refresh(); }, [refresh]);

  async function upload(file?: File) {
    if (!file || !token) return;
    setBusy(true);
    setError("");
    try {
      const invoice = await extractInvoice(file, token);
      setInvoices(current => [invoice, ...current.filter(item => item.id !== invoice.id)]);
      setSelectedId(invoice.id);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not process invoice");
    } finally {
      setBusy(false);
    }
  }

  if (!token) return <main className="login-shell">
    <section className="login-card">
      <div className="brand-mark">L</div>
      <span className="eyebrow">Invoice automation workspace</span>
      <h1>Turn invoices into reliable data.</h1>
      <p>Upload a PDF, validate extracted totals and keep every processed invoice in one calm workspace.</p>
      <GoogleLogin
        onSuccess={({credential}) => {
          if (!credential) return;
          sessionStorage.setItem(TOKEN_KEY, credential);
          setToken(credential);
        }}
        onError={() => setError("Google sign-in was not completed")}
        useOneTap
      />
      {error && <p className="error" role="alert">{error}</p>}
      <small>Access is restricted to members configured for this environment.</small>
    </section>
    <div className="login-art" aria-hidden="true"><div className="paper"><i/><i/><i/><b/></div></div>
  </main>;

  return <div className="app-shell">
    <header>
      <div className="brand"><span className="brand-mark small">L</span><div><strong>Ledgerly</strong><small>Invoice workspace</small></div></div>
      <button className="ghost" onClick={() => { googleLogout(); sessionStorage.removeItem(TOKEN_KEY); setToken(""); }}>Sign out</button>
    </header>
    <main className="workspace">
      <section className="hero-row">
        <div><span className="eyebrow">Overview</span><h1>Invoices, without the busywork.</h1><p>Extract structured data and review it before it moves downstream.</p></div>
        <label className={busy ? "upload disabled" : "upload"}>
          <input type="file" accept="application/pdf" disabled={busy} onChange={event => void upload(event.target.files?.[0])}/>
          <span>{busy ? "Processing…" : "Upload invoice"}</span><small>PDF · up to 10 MB</small>
        </label>
      </section>
      {error && <div className="error banner" role="alert">{error}<button onClick={() => setError("")}>Dismiss</button></div>}
      <section className="content-grid">
        <div className="invoice-list">
          <div className="section-title"><div><span className="eyebrow">Recent activity</span><h2>Processed invoices</h2></div><button className="ghost" onClick={() => void refresh()} disabled={busy}>Refresh</button></div>
          {invoices.length === 0 && !busy ? <div className="empty"><span>⌁</span><h3>No invoices yet</h3><p>Upload your first PDF to see extracted fields here.</p></div> :
            <div className="table-wrap"><table><thead><tr><th>Vendor</th><th>Invoice</th><th>Date</th><th>Total</th><th>Status</th></tr></thead><tbody>
              {invoices.map(invoice => <tr key={invoice.id} className={selected?.id === invoice.id ? "selected" : ""} onClick={() => setSelectedId(invoice.id)}>
                <td><strong>{invoice.vendor_name}</strong><small>{invoice.source_filename}</small></td><td>{invoice.invoice_number}</td><td>{invoice.invoice_date}</td><td>{money(invoice.total, invoice.currency)}</td><td><span className={invoice.totals_check.is_consistent ? "dot valid" : "dot warning"}/>{invoice.totals_check.is_consistent ? "Verified" : "Review"}</td>
              </tr>)}
            </tbody></table></div>}
        </div>
        {selected ? <InvoicePanel invoice={selected}/> : <aside className="detail-panel placeholder"><p>Select an invoice to inspect its extracted data.</p></aside>}
      </section>
    </main>
  </div>;
}
