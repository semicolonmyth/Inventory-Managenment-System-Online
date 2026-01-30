import { serve } from "https://deno.land/std@0.168.0/http/server.ts"
import { createClient } from "https://esm.sh/@supabase/supabase-js@2"

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
}

serve(async (req) => {
  // Handle CORS preflight
  if (req.method === 'OPTIONS') {
    return new Response('ok', { headers: corsHeaders })
  }

  try {
    // Get Supabase client
    const supabaseClient = createClient(
      Deno.env.get('SUPABASE_URL') ?? '',
      Deno.env.get('SUPABASE_ANON_KEY') ?? '',
      {
        global: {
          headers: { Authorization: req.headers.get('Authorization')! },
        },
      }
    )

    // Get request body
    const { license_key } = await req.json()

    if (!license_key) {
      return new Response(
        JSON.stringify({ valid: false, error: 'License key is required.' }),
        {
          status: 400,
          headers: { ...corsHeaders, 'Content-Type': 'application/json' },
        }
      )
    }

    // Get license secret from environment
    const LICENSE_SECRET = Deno.env.get('LICENSE_SECRET')
    if (!LICENSE_SECRET) {
      console.error('LICENSE_SECRET not configured')
      return new Response(
        JSON.stringify({ valid: false, error: 'Server configuration error.' }),
        {
          status: 500,
          headers: { ...corsHeaders, 'Content-Type': 'application/json' },
        }
      )
    }

    // Query licenses table
    const { data: license, error: queryError } = await supabaseClient
      .from('licenses')
      .select('*')
      .eq('key', license_key)
      .single()

    if (queryError || !license) {
      return new Response(
        JSON.stringify({ valid: false, error: 'License key not found.' }),
        {
          status: 200,
          headers: { ...corsHeaders, 'Content-Type': 'application/json' },
        }
      )
    }

    // Check if license is active
    if (!license.is_active) {
      return new Response(
        JSON.stringify({ valid: false, error: 'License is deactivated.' }),
        {
          status: 200,
          headers: { ...corsHeaders, 'Content-Type': 'application/json' },
        }
      )
    }

    // Check expiration
    const expiryDate = new Date(license.expiry_date)
    const now = new Date()

    if (now > expiryDate) {
      return new Response(
        JSON.stringify({ valid: false, error: 'License has expired.' }),
        {
          status: 200,
          headers: { ...corsHeaders, 'Content-Type': 'application/json' },
        }
      )
    }

    // License is valid - generate HMAC signature
    const encoder = new TextEncoder()
    const keyData = encoder.encode(LICENSE_SECRET)
    const user_id = license.user_id || ''
    const expiry = license.expiry_date
    const message = `${license_key}${user_id}${expiry}`
    const messageData = encoder.encode(message)

    // Import crypto for HMAC
    const key = await crypto.subtle.importKey(
      'raw',
      keyData,
      { name: 'HMAC', hash: 'SHA-256' },
      false,
      ['sign']
    )

    const signatureBuffer = await crypto.subtle.sign('HMAC', key, messageData)
    const signatureArray = Array.from(new Uint8Array(signatureBuffer))
    const signature = signatureArray.map(b => b.toString(16).padStart(2, '0')).join('')

    // Return success response
    return new Response(
      JSON.stringify({
        valid: true,
        user_id: license.user_id || '',
        expiry: expiry,
        plan_type: license.plan_type || 'monthly',
        signature: signature,
      }),
      {
        status: 200,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' },
      }
    )
  } catch (error) {
    console.error('Error:', error)
    return new Response(
      JSON.stringify({ valid: false, error: 'Internal server error.' }),
      {
        status: 500,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' },
      }
    )
  }
})

