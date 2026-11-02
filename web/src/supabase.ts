import { createClient } from "@supabase/supabase-js";

const url = import.meta.env.VITE_SUPABASE_URL;
const key = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY; // public by design; the secret key never reaches the browser

export const googleEnabled = import.meta.env.VITE_AUTH_GOOGLE === "true";

// PKCE keeps tokens out of URLs when returning from Google or a password-reset email.
export const supabase = url && key ? createClient(url, key, { auth: { flowType: "pkce" } }) : null;
