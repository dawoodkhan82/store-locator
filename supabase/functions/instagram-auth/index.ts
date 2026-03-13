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
    const { code, redirectUri } = await req.json();

    if (!code || !redirectUri) {
      return new Response(
        JSON.stringify({ error: "Missing code or redirectUri" }),
        { status: 400, headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    const INSTAGRAM_APP_ID = Deno.env.get("INSTAGRAM_APP_ID")!;
    const INSTAGRAM_APP_SECRET = Deno.env.get("INSTAGRAM_APP_SECRET")!;
    const SUPABASE_URL = Deno.env.get("SUPABASE_URL")!;
    const SUPABASE_SERVICE_ROLE_KEY = Deno.env.get("SB_SECRET_KEY")!;

    // Step 1: Exchange code for short-lived token
    const tokenParams = new URLSearchParams({
      client_id: INSTAGRAM_APP_ID,
      client_secret: INSTAGRAM_APP_SECRET,
      grant_type: "authorization_code",
      redirect_uri: redirectUri,
      code: code,
    });

    const shortTokenRes = await fetch("https://api.instagram.com/oauth/access_token", {
      method: "POST",
      body: tokenParams,
    });

    const shortTokenData = await shortTokenRes.json();

    if (shortTokenData.error_message) {
      throw new Error(shortTokenData.error_message);
    }

    const shortLivedToken = shortTokenData.access_token;
    const instagramUserId = shortTokenData.user_id?.toString();

    // Step 2: Exchange short-lived token for long-lived token (60 days)
    const longTokenRes = await fetch(
      `https://graph.instagram.com/access_token?grant_type=ig_exchange_token&client_secret=${INSTAGRAM_APP_SECRET}&access_token=${shortLivedToken}`
    );

    const longTokenData = await longTokenRes.json();
    const longLivedToken = longTokenData.access_token || shortLivedToken;
    const expiresIn = longTokenData.expires_in || 5184000; // 60 days default

    // Step 3: Fetch Instagram profile
    const profileRes = await fetch(
      `https://graph.instagram.com/me?fields=id,username&access_token=${longLivedToken}`
    );

    const profileData = await profileRes.json();
    const username = profileData.username || `user_${instagramUserId}`;

    // Step 4: Create Supabase admin client
    const supabaseAdmin = createClient(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY);

    // Step 5: Create or get auth user
    const email = `${instagramUserId}@instagram.placeholder`;
    let userId: string;

    // Try to find existing user by email
    const { data: existingUsers } = await supabaseAdmin.auth.admin.listUsers();
    const existingUser = existingUsers?.users?.find((u) => u.email === email);

    if (existingUser) {
      userId = existingUser.id;
    } else {
      // Create new user
      const { data: newUser, error: createError } = await supabaseAdmin.auth.admin.createUser({
        email: email,
        email_confirm: true,
        user_metadata: { instagram_user_id: instagramUserId, instagram_username: username },
      });

      if (createError) throw createError;
      userId = newUser.user.id;
    }

    // Step 6: Upsert user data in public.users
    const tokenExpiry = new Date(Date.now() + expiresIn * 1000).toISOString();

    await supabaseAdmin.from("users").upsert({
      id: userId,
      instagram_user_id: instagramUserId,
      instagram_username: username,
      access_token: longLivedToken,
      token_expiry: tokenExpiry,
      updated_at: new Date().toISOString(),
    });

    // Step 7: Generate session for the user
    const { data: sessionData, error: sessionError } =
      await supabaseAdmin.auth.admin.generateLink({
        type: "magiclink",
        email: email,
      });

    // Use signInWithPassword or create a session directly
    // For simplicity, generate a session token
    const { data: signInData, error: signInError } =
      await supabaseAdmin.auth.admin.generateLink({
        type: "magiclink",
        email: email,
      });

    // Alternative: create session directly
    const { data: session } = await supabaseAdmin.auth.admin.createUser({
      email: email,
      email_confirm: true,
    }).catch(() => ({ data: null }));

    // Generate access token for client
    const { data: tokenData } = await supabaseAdmin.auth.admin.generateLink({
      type: "magiclink",
      email: email,
    });

    // Sign in on behalf of user to get session tokens
    const tempAuthToken = `ig_${instagramUserId}_${Date.now()}`;
    await supabaseAdmin.auth.admin.updateUser(userId, { password: tempAuthToken });

    const { data: authSession, error: authError } = await supabaseAdmin.auth.signInWithPassword({
      email: email,
      password: tempAuthToken,
    });

    if (authError) {
      throw new Error("Failed to create session: " + authError.message);
    }

    return new Response(
      JSON.stringify({
        username: username,
        access_token: authSession.session?.access_token,
        refresh_token: authSession.session?.refresh_token,
        user_id: userId,
      }),
      { headers: { ...corsHeaders, "Content-Type": "application/json" } }
    );
  } catch (error) {
    console.error("Instagram auth error:", error);
    return new Response(
      JSON.stringify({ error: error.message || "Authentication failed" }),
      { status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" } }
    );
  }
});
