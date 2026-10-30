import { render, screen } from "@testing-library/react";
import { GoogleOAuthProvider } from "@react-oauth/google";
import { beforeEach, expect, test, vi } from "vitest";
import App from "./App";

beforeEach(() => {
  sessionStorage.clear();
  vi.stubGlobal("fetch", vi.fn());
});

test("asks an unauthenticated user to sign in", () => {
  render(<GoogleOAuthProvider clientId="test-client"><App /></GoogleOAuthProvider>);
  expect(screen.getByRole("heading", {name: /turn invoices into reliable data/i})).toBeInTheDocument();
  expect(screen.getByText(/access is restricted/i)).toBeInTheDocument();
});

test("shows the signed-in user's invoices", async () => {
  sessionStorage.setItem("invoice-google-id-token", "signed-token");
  vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify([{
    id: 7,
    source_filename: "october.pdf",
    created_by: "user-1",
    created_at: "2026-10-30T09:00:00Z",
    vendor_name: "Northstar Supplies",
    invoice_number: "INV-700",
    invoice_date: "2026-10-29",
    currency: "GBP",
    subtotal: "100.00",
    tax: "20.00",
    total: "120.00",
    totals_check: {expected_total: "120.00", difference: "0.00", is_consistent: true}
  }]), {status: 200, headers: {"Content-Type": "application/json"}}));

  render(<GoogleOAuthProvider clientId="test-client"><App /></GoogleOAuthProvider>);

  expect(await screen.findAllByText("Northstar Supplies")).toHaveLength(2);
  expect(screen.getByText("Totals verified")).toBeInTheDocument();
  expect(fetch).toHaveBeenCalledWith("/api/v1/invoices", expect.objectContaining({headers: expect.any(Headers)}));
});
