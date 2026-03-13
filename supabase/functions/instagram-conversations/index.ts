import { serve } from "https://deno.land/std@0.177.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
};

serve(async (req) => {
  if (req.method === "OPTIONS") {
    return new Response("ok", { headers: corsHeaders });
  }

  try {
    const SUPABASE_URL = Deno.env.get("SUPABASE_URL")!;
    const SUPABASE_SERVICE_ROLE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;

    // Verify JWT from Authorization header
    const authHeader = req.headers.get("Authorization");
    if (!authHeader) {
      return new Response(
        JSON.stringify({ error: "Missing authorization header" }),
        { status: 401, headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    const supabaseClient = createClient(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY);

    // Verify the JWT and get user
    const token = authHeader.replace("Bearer ", "");
    const { data: { user }, error: authError } = await createClient(
      SUPABASE_URL,
      Deno.env.get("SUPABASE_ANON_KEY")!
    ).auth.getUser(token);

    if (authError || !user) {
      return new Response(
        JSON.stringify({ error: "Invalid token" }),
        { status: 401, headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    // Get user's Instagram access token and page ID
    const { data: userData, error: userError } = await supabaseClient
      .from("users")
      .select("access_token, page_id, instagram_user_id")
      .eq("id", user.id)
      .single();

    if (userError || !userData?.access_token) {
      return new Response(
        JSON.stringify({ error: "Instagram not connected" }),
        { status: 400, headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    const { access_token, page_id, instagram_user_id } = userData;

    // Fetch conversations from Instagram Graph API
    // Note: requires instagram_manage_messages permission (Meta App Review)
    const conversationsUrl = page_id
      ? `https://graph.facebook.com/v18.0/${page_id}/conversations?fields=participants,messages{message,from,created_time,is_unsupported}&platform=instagram&access_token=${access_token}`
      : `https://graph.instagram.com/v18.0/me/conversations?fields=participants,messages{message,from,created_time}&access_token=${access_token}`;

    const convRes = await fetch(conversationsUrl);
    const convData = await convRes.json();

    if (convData.error) {
      console.error("Instagram API error:", convData.error);
      return new Response(
        JSON.stringify({ error: convData.error.message || "Instagram API error" }),
        { status: 400, headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    const conversations = convData.data || [];

    // Get existing DM records for this user
    const { data: dmRecords } = await supabaseClient
      .from("dm_records")
      .select("store_key, instagram_handle, status, api_status")
      .eq("user_id", user.id);

    const dmRecordMap = new Map(
      (dmRecords || []).map((r) => [r.instagram_handle?.toLowerCase(), r])
    );

    // Match conversations to store handles and detect statuses
    const dmUpdates: Array<{
      instagram_handle: string;
      status: string;
      seen_at?: string;
      responded_at?: string;
    }> = [];

    for (const conv of conversations) {
      const participants = conv.participants?.data || [];
      const messages = conv.messages?.data || [];

      // Find the other participant (not our account)
      const otherParticipant = participants.find(
        (p: { id: string }) => p.id !== instagram_user_id
      );

      if (!otherParticipant?.username) continue;

      const handle = otherParticipant.username.toLowerCase();
      const dmRecord = dmRecordMap.get(handle);

      if (!dmRecord) continue; // Not a tracked store

      // Determine conversation status
      let status = "contacted";
      let seenAt: string | undefined;
      let respondedAt: string | undefined;

      if (messages.length > 0) {
        const latestMessage = messages[0];
        const latestFrom = latestMessage.from?.username?.toLowerCase();

        if (latestFrom && latestFrom === handle) {
          // They sent the last message = they responded
          status = "responded";
          respondedAt = latestMessage.created_time;
        } else {
          // We sent the last message — check if it was read
          // Note: read receipts require specific API fields
          status = "seen"; // Default to seen if conversation exists
          seenAt = latestMessage.created_time;
        }
      }

      // Only update if status changed
      if (dmRecord.api_status !== status) {
        dmUpdates.push({ instagram_handle: handle, status, seen_at: seenAt, responded_at: respondedAt });

        // Update in database
        await supabaseClient
          .from("dm_records")
          .update({
            api_status: status,
            ...(seenAt && { api_seen_at: seenAt }),
            ...(respondedAt && { api_responded_at: respondedAt }),
            updated_at: new Date().toISOString(),
          })
          .eq("user_id", user.id)
          .eq("instagram_handle", handle);
      }
    }

    return new Response(
      JSON.stringify({
        conversations: conversations,
        dm_updates: dmUpdates,
        fetched_at: new Date().toISOString(),
      }),
      { headers: { ...corsHeaders, "Content-Type": "application/json" } }
    );
  } catch (error) {
    console.error("Conversations fetch error:", error);
    return new Response(
      JSON.stringify({ error: error.message || "Failed to fetch conversations" }),
      { status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" } }
    );
  }
});
