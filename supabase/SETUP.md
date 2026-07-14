# EXOS Runtime Setup

1. Create one Supabase project for EXOS.
2. Open **SQL Editor** in Supabase.
3. Run the complete `supabase/runtime_schema.sql` file.
4. Copy the project URL, publishable key, and secret key from Supabase project settings.
5. Add these keys to the Streamlit secrets for Admin, Facilitator, and Participant:

```toml
SUPABASE_URL="https://YOUR-PROJECT.supabase.co"
SUPABASE_PUBLISHABLE_KEY="YOUR-PUBLISHABLE-KEY"
```

6. Add the secret key only to Admin and Facilitator. The Participant app does not need it:

```toml
SUPABASE_SECRET_KEY="YOUR-SECRET-KEY"
```

7. Reboot all three Streamlit apps.
8. In **Event Manager → Live Registration Runtime**, publish the test event.
9. Select the reset option only for a test event or before registration opens. It deletes that event's runtime participants.

Never commit these keys to Git.
