import { serve } from "https://deno.land/std@0.177.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
};

serve(async (req) => {
  const VERIFY_TOKEN = Deno.env.get("WEBHOOK_VERIFY_TOKEN") || "store_scraper_webhook_verify";
  const SUPABASE_URL = Deno.env.get("SUPABASE_URL")!;
  const SUPABASE_SERVICE_ROLE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;

  // GET: Meta webhook verification
  if (req.method === "GET") {
    const url = new URL(req.url);
    const mode = url.searchParams.get("hub.mode");
    const token = url.searchParams.get("hub.verify_token");
    const challenge = url.searchParams.get("hub.challenge");

    if (mode === "subscribe" && token === VERIFY_TOKEN) {
      console.log("Webhook verified");
      return new Response(challenge, { status: 200 });
    }

    return new Response("Forbidden", { status: 403 });
  }

  // POST: Process webhook events
  if (req.method === "POST") {
    try {
      const body = await req.json();
      const supabaseAdmin = createClient(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY);

      // Process each entry
      for (const entry of body.entry || []) {
        const messagingEvents = entry.messaging || [];

        for (const event of messagingEvents) {
          const senderId = event.sender?.id;
          const recipientId = event.recipient?.id;

          if (!senderId || !recipientId) continue;

          // Message received
          if (event.message) {
            console.log(`Message from ${senderId}: ${event.message.text?.substring(0, 50)}`);

            // Find the user who owns this Instagram account (recipient)
            const { data: userData } = await supabaseAdmin
              .from("users")
              .select("id, instagram_user_id")
              .or(`instagram_user_id.eq.${recipientId},page_id.eq.${recipientId}`)
              .single();

            if (userData) {
              // Find DM record for this sender
              // We need to look up by Instagram user ID, but we store handles
              // This requires an additional API call or stored mapping
              // For now, update any record where we can match
              await supabaseAdmin
                .from("dm_records")
                .update({
                  api_status: "responded",
                  api_responded_at: new Date().toISOString(),
                  updated_at: new Date().toISOString(),
                })
                .eq("user_id", userData.id)
                .eq("api_status", "seen"); // Only update seen -> responded
            }
          }

          // Message read/delivery event
          if (event.read) {
            console.log(`Message read by ${senderId} at ${event.read.watermark}`);

            const { data: userData } = await supabaseAdmin
              .from("users")
              .select("id")
              .or(`instagram_user_id.eq.${recipientId},page_id.eq.${recipientId}`)
              .single();

            if (userData) {
              // Mark messages as seen for this conversation
              await supabaseAdmin
                .from("dm_records")
                .update({
                  api_status: "seen",
                  api_seen_at: new Date().toISOString(),
                  updated_at: new Date().toISOString(),
                })
                .eq("user_id", userData.id)
                .eq("api_status", "contacted"); // Only update contacted -> seen
            }
          }

          // Delivery event
          if (event.delivery) {
            console.log(`Message delivered to ${senderId}`);
          }
        }
      }

      return new Response(
        JSON.stringify({ status: "ok" }),
        { headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    } catch (error) {
      console.error("Webhook processing error:", error);
      // Always return 200 for webhooks to prevent Meta from disabling them
      return new Response(
        JSON.stringify({ status: "error", message: error.message }),
        { status: 200, headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }
  }

  return new Response("Method not allowed", { status: 405 });
});
