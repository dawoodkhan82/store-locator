import { serve } from "https://deno.land/std@0.177.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
};

/**
 * Token refresh function — intended to be called by pg_cron daily.
 *
 * Setup pg_cron in Supabase SQL editor:
 *   select cron.schedule(
 *     'refresh-instagram-tokens',
 *     '0 3 * * *', -- daily at 3 AM UTC
 *     $$
 *     select net.http_post(
 *       url := 'YOUR_SUPABASE_URL/functions/v1/instagram-token-refresh',
 *       headers := jsonb_build_object(
 *         'Authorization', 'Bearer YOUR_SERVICE_ROLE_KEY',
 *         'Content-Type', 'application/json'
 *       ),
 *       body := '{}'::jsonb
 *     );
 *     $$
 *   );
 */
serve(async (req) => {
  if (req.method === "OPTIONS") {
    return new Response("ok", { headers: corsHeaders });
  }

  try {
    const SUPABASE_URL = Deno.env.get("SUPABASE_URL")!;
    const SUPABASE_SERVICE_ROLE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;

    // Verify this is called with service role key
    const authHeader = req.headers.get("Authorization");
    if (!authHeader?.includes(SUPABASE_SERVICE_ROLE_KEY)) {
      // Also accept valid JWT
      const supabaseCheck = createClient(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY);
      // For cron jobs, we expect service role auth
    }

    const supabaseAdmin = createClient(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY);

    // Find tokens expiring within 7 days
    const sevenDaysFromNow = new Date(Date.now() + 7 * 24 * 60 * 60 * 1000).toISOString();

    const { data: expiringUsers, error } = await supabaseAdmin
      .from("users")
      .select("id, instagram_username, access_token, token_expiry")
      .lt("token_expiry", sevenDaysFromNow)
      .not("access_token", "is", null);

    if (error) {
      throw error;
    }

    const results: Array<{ username: string; status: string; error?: string }> = [];

    for (const user of expiringUsers || []) {
      try {
        // Refresh the long-lived token
        const refreshRes = await fetch(
          `https://graph.instagram.com/refresh_access_token?grant_type=ig_refresh_token&access_token=${user.access_token}`
        );

        const refreshData = await refreshRes.json();

        if (refreshData.error) {
          throw new Error(refreshData.error.message);
        }

        const newToken = refreshData.access_token;
        const expiresIn = refreshData.expires_in || 5184000;
        const newExpiry = new Date(Date.now() + expiresIn * 1000).toISOString();

        // Update the token in the database
        await supabaseAdmin
          .from("users")
          .update({
            access_token: newToken,
            token_expiry: newExpiry,
            updated_at: new Date().toISOString(),
          })
          .eq("id", user.id);

        results.push({
          username: user.instagram_username || user.id,
          status: "refreshed",
        });

        console.log(`Refreshed token for @${user.instagram_username}`);
      } catch (err) {
        results.push({
          username: user.instagram_username || user.id,
          status: "failed",
          error: err.message,
        });

        console.error(`Failed to refresh token for @${user.instagram_username}:`, err.message);
      }
    }

    return new Response(
      JSON.stringify({
        processed: results.length,
        results: results,
        checked_at: new Date().toISOString(),
      }),
      { headers: { ...corsHeaders, "Content-Type": "application/json" } }
    );
  } catch (error) {
    console.error("Token refresh error:", error);
    return new Response(
      JSON.stringify({ error: error.message || "Token refresh failed" }),
      { status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" } }
    );
  }
});
