import { useCallback, useEffect, useMemo, useState } from "react";
import { extractInvoice, InvoiceRecord, listInvoices } from "../api";

export function useInvoices(token: string) {
  const [invoices, setInvoices] = useState<InvoiceRecord[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const selected = useMemo(() => invoices.find(item => item.id === selectedId) ?? invoices[0], [invoices, selectedId]);
  const refresh = useCallback(async () => {
    if (!token) return;
    setBusy(true); setError("");
    try { const records = await listInvoices(token); setInvoices(records); setSelectedId(current => current ?? records[0]?.id ?? null); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Could not load invoices"); }
    finally { setBusy(false); }
  }, [token]);
  useEffect(() => { void refresh(); }, [refresh]);
  const upload = useCallback(async (file?: File) => {
    if (!file || !token) return;
    setBusy(true); setError("");
    try { const invoice = await extractInvoice(file, token); setInvoices(current => [invoice, ...current.filter(item => item.id !== invoice.id)]); setSelectedId(invoice.id); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Could not process invoice"); }
    finally { setBusy(false); }
  }, [token]);
  return {invoices, selected, selectedId, setSelectedId, busy, error, setError, refresh, upload};
}
