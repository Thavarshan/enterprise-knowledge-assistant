# Production API in Postman

Import both JSON files in this directory into Postman:

- `viridian-production.postman_collection.json`
- `viridian-production.postman_environment.json`

Select the **Viridian - Production** environment.
The production API URL is already set. The environment defaults to the analyst
account; copy its public demo password from the root README into the `pass`
secret variable. The password is intentionally blank in the checked-in file.

## Request order

1. Send **Health**, **Version and model**, or **Readiness** for public status
   responses.
2. Send **Login**. On success, its script stores the bearer token in
   `accessToken`.
3. Send **Who am I?** to see the role assigned by the API.
4. Send **List my sessions**. If it returns no sessions, send **Create a
   session** first. These requests set `sid` for the remaining requests.
5. Send **Get session history** to see persisted JSON messages, or **Send chat
   message (live model)** to see an SSE response.

Change `user` to `viewer`, `analyst`, or `admin` to exercise each account.
The live chat request calls the configured provider and may incur API usage.
