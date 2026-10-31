# Running family-hub on a Synology NAS (or any Docker system)

The hub runs as two containers from images on GitHub Container Registry (GHCR):

- **backend** (`ghcr.io/frankandreas/family-hub/backend`): the API, with the SQLite database and the key that signs
  the logins in `./data`
- **frontend** (`ghcr.io/frankandreas/family-hub/frontend`): nginx serving the start page on port 8080 inside the
  container, forwarding `/api` and `/.well-known/jwks.json` to the backend

It sits next to the other family apps on one NAS (budget 8081, job tracking 8082, meal planner 8085, hub **8086**).

## Prerequisites

- A Synology NAS with **Container Manager** (Docker) and SSH access (**Control Panel → Terminal & SNMP**).
- The `*.local.<domain>` DNS record and wildcard certificate from family-budget-dashboard (its README_DOCKER.md,
  "HTTPS at home"). The hub's cookie needs HTTPS.
- For logins from outside: the Cloudflare Tunnel and Cloudflare Access the other apps already use.

## Installation

1. **Choose the user the hub runs as.** Reuse the DSM user of the other family apps and look up its IDs: `id <user>`
   (e.g. `uid=1031 gid=100`).
2. **Prepare the folder.** Create `/volume1/docker/family-hub`, upload `docker-compose.yml` into it **renamed to
   `compose.yaml`**, and create the data folder, owned by that user:
   ```bash
   cd /volume1/docker/family-hub
   sudo mkdir -p data
   sudo chown -R 1031:100 data    # the IDs from step 1, or 999:999
   sudo chmod 700 data            # the PIN hashes and the signing key: for the hub only
   ```
3. **Create `.env`** (see `.env.example` for all settings):
   ```bash
   printf 'PUID=1031\nPGID=100\nPORT=8086\nCOOKIE_DOMAIN=local.<domain>\n' | sudo tee .env
   sudo chmod 600 .env
   ```
   There is no `SECRET_KEY`: the backend makes its signing key on the first start and keeps it in
   `data/signing-key.pem`.
4. **Start** it:
   ```bash
   sudo docker-compose pull
   sudo docker-compose up -d
   ```

### At home: HTTPS and the cookie

1. **Control Panel → Login Portal → Advanced → Reverse Proxy → Create**: source HTTPS, `home.local.<domain>`, port 443,
   **Enable HSTS**; destination HTTP, `localhost`, port 8086.
2. **Control Panel → Security → Certificate → Settings**: pick the `*.local.<domain>` certificate for the new entry.
3. `COOKIE_DOMAIN=local.<domain>` in `.env` (step 3 above): the login then counts for every app at
   `*.local.<domain>`, and browsers never send it to the outside addresses.
4. Open `https://home.local.<domain>` and save it to the home screen of the iPad and the phones.

### First login

On an empty database the backend creates the parent **Admin** with a random 4-digit PIN, printed once in its log:

```bash
sudo docker logs hub-backend 2>&1 | grep "INITIAL PIN"
```

Log in as `Admin`, then in **Einstellungen**:
- change the PIN and rename Admin;
- add the family under **Personen**, with e-mail addresses for whoever logs in from outside;
- add the apps under **Apps**: home address (`https://budget.local.<domain>`), and an outside address only for apps
  with a tunnel route. An app that uses the family login also gets its **app key** (as in the app's own guide, e.g.
  `budget`) and the people who may use it: only they see its tile and get in.

To choose the first PIN yourself, set `INITIAL_ADMIN_PIN=1234` in `.env` before the first start.

Each parent changes only their own PIN and details; parents set the children's PINs. Logins from before an update to
this rule may show "Log in again to change this" once: managing needs a second cookie that only the hub gets.

### Forgot PIN: reset by e-mail

With these in `.env`, the login screen offers **Forgot PIN?** for people with an e-mail address. The hub mails a link
that works once, for 30 minutes, at home only:

- `RESEND_API_KEY`: an API key from [Resend](https://resend.com) (the same account as family-job-tracking's reminders
  works), allowed to send from your domain;
- `MAIL_FROM`: the sender, e.g. `Familien-Hub <hub@<domain>>`;
- `HUB_PUBLIC_URL`: the hub's address at home, `https://home.local.<domain>`.

Without all three, there's no **Forgot PIN?**. The last resort, also for people without an address, is a link printed
on the NAS:

```bash
sudo docker exec hub-backend python -m app.reset_pin <name>
```

An e-mail address someone enters counts only once the person opens the link mailed to it (24 hours, at home): until
then it shows as "waiting for confirmation" and is neither the Cloudflare login nor the way back in. Addresses from
before this rule stay as they were. Without the mail settings, or when the mail is lost, print the link on the NAS:

```bash
sudo docker exec hub-backend python -m app.confirm_email <name>
```

### From outside: Cloudflare Tunnel and Access

**Only through the Cloudflare tunnel, never a port forward.** The hub tells home from outside by the header
`Cf-Connecting-Ip`, which Cloudflare sets on everything through the tunnel. A router port forward to the NAS or the DSM
reverse proxy brings requests without it: they would count as at home, with the PIN login and managing people.

Same setup as the other apps' outside access (family-job-tracking's README_DOCKER.md). Cloudflare renames dashboard
menus from time to time.

1. **Tunnel route.** **Zero Trust → Networks → Connectors → Cloudflare Tunnels** → the NAS's tunnel →
   **Published application routes → Add**: subdomain `home`, your domain, service `HTTP`, URL `<NAS_IP>:8086`.
2. **Access application.** **Access controls → Applications**: add `home.<domain>` to the family application, or make
   one with the family's e-mail policy. Note its **Application Audience (AUD) Tag**.
3. **`.env`**: `CF_TEAM_DOMAIN=<team>.cloudflareaccess.com` and `CF_AUDIENCE=<the AUD tag>`. When apps pass their
   visitors' Cloudflare tokens to the hub, add their applications' AUD tags too, comma-separated. Then
   `sudo docker-compose up -d`.
4. **Each app's tile** (Settings → Apps → the app → "Cloudflare Access: the AUD tag of this app's application"): with
   its own application's tag there, the hub takes a Cloudflare login for that app only when Cloudflare made it for that
   application, so a login leaked from another family app or the hub gets nowhere. Optional; without it any tag in
   `CF_AUDIENCE` counts. Only with one Access application per app: tiles sharing one application gain nothing.

An app stays home-only when the tunnel has no route for it (like family-budget-dashboard). Give such an app no
outside address in the hub.

### Where the data is

`data/` holds the database `hub.db` and `signing-key.pem`. Back up the whole folder, and keep the backup private: the
PIN hashes in it fall to a brute force (4 digits), and the key signs logins for every app. Without the key, every
login ends and the apps must fetch the new public key.

## Automatic updates

`scripts/nas-update.sh` works as in the other family apps: it pulls the images, backs up the database to
`db-backups/` if there is a new one, keeps the old images as `:previous`, restarts and waits until the backend is
healthy (`logs/update.log`).

1. Copy `scripts/nas-update.sh` into `/volume1/docker/family-hub` and make it executable (or let
   `scripts/deploy-nas.sh` upload it):
   ```bash
   sudo chmod +x /volume1/docker/family-hub/nas-update.sh
   sudo /volume1/docker/family-hub/nas-update.sh     # should end with "Up to date" or "Update complete"
   ```
2. **Control Panel → Task Scheduler → Create → Scheduled Task → User-defined script**: user **root**, daily a few
   minutes apart from the other apps, command `bash /volume1/docker/family-hub/nas-update.sh`.

To deploy right away from your computer:
```bash
cp .deploy.env.example .deploy.env   # once; then set NAS_HOST and NAS_DIR
scripts/deploy-nas.sh
```

### Rolling back an update

First **disable the scheduled task**, otherwise the next night installs the same version again. Then:

```bash
cd /volume1/docker/family-hub
sudo docker tag ghcr.io/frankandreas/family-hub/backend:previous ghcr.io/frankandreas/family-hub/backend:latest
sudo docker tag ghcr.io/frankandreas/family-hub/frontend:previous ghcr.io/frankandreas/family-hub/frontend:latest
sudo docker stop hub-backend
sudo sh -c 'gunzip -c db-backups/hub-YYYYMMDD-HHMMSS.sqlite.gz > data/hub.db'
sudo docker-compose up -d backend frontend
```
