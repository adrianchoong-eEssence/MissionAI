insert into storage.buckets (
    id,
    name,
    public,
    file_size_limit,
    allowed_mime_types
)
values (
    'exos-submissions',
    'exos-submissions',
    false,
    5242880,
    array[
        'image/jpeg',
        'image/png',
        'image/webp'
    ]
)
on conflict (id) do update
set public = excluded.public,
    file_size_limit = excluded.file_size_limit,
    allowed_mime_types = excluded.allowed_mime_types;

-- No anon or authenticated storage policies are created. Uploads and signed
-- downloads are performed only by the server-side Streamlit application using
-- the Supabase secret key, which bypasses Storage RLS.
