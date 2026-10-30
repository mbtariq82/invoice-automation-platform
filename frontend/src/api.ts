export type TotalsCheck = {
  expected_total: string;
  difference: string;
  is_consistent: boolean;
};

export type InvoiceRecord = {
  id: number;
  source_filename: string | null;
  created_by: string | null;
  created_at: string;
  vendor_name: string;
  invoice_number: string;
  invoice_date: string;
  currency: string;
  subtotal: string;
  tax: string;
  total: string;
  totals_check: TotalsCheck;
  cached?: boolean;
};

async function request<T>(path: string, token: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  headers.set("Authorization", `Bearer ${token}`);
  const baseUrl = window.__APP_CONFIG__?.apiBaseUrl ?? "";
  const response = await fetch(`${baseUrl}/v1${path}`, {...init, headers});
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const body = await response.json() as {detail?: string};
      if (body.detail) message = body.detail;
    } catch {
      // Keep the status-based message for non-JSON proxy errors.
    }
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}

export const listInvoices = (token: string) => request<InvoiceRecord[]>("/invoices", token);

export function extractInvoice(file: File, token: string) {
  const form = new FormData();
  form.append("file", file);
  return request<InvoiceRecord>("/invoices/extract", token, {method: "POST", body: form});
}
