import { useCallback, useState } from "react";
import { googleLogout } from "@react-oauth/google";

const TOKEN_KEY = "invoice-google-id-token";

export function useAuth() {
  const [token, setToken] = useState(() => sessionStorage.getItem(TOKEN_KEY) ?? "");
  const signIn = useCallback((credential: string) => {
    sessionStorage.setItem(TOKEN_KEY, credential);
    setToken(credential);
  }, []);
  const signOut = useCallback(() => {
    googleLogout();
    sessionStorage.removeItem(TOKEN_KEY);
    setToken("");
  }, []);
  return {token, signIn, signOut};
}
