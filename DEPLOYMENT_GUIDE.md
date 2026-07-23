# SwapScholar Azure VM deployment

This guide installs the functional app without deleting the existing proposal
website. Keep the proposal backup until the new application has been tested.

## Updating an existing SwapScholar installation

The update package can be applied without deleting accounts, skills, exchanges,
reviews or credits. The SQLite database lives in the separate `instance`
directory and the new private-message table is created automatically at startup.

```bash
sudo cp /var/www/swapscholar/instance/swapscholar.sqlite \
  /var/www/swapscholar/instance/swapscholar-before-chat.sqlite
sudo unzip -o ~/swapscholar-vm-ready.zip -d /var/www/swapscholar
sudo chown -R www-data:www-data /var/www/swapscholar
sudo systemctl restart swapscholar
sudo systemctl status swapscholar --no-pager
```

Do not run `init-db` or `seed-demo` during an update.

## 1. Upload the package

Upload the supplied ZIP file to the Ubuntu user's home folder using Azure SSH,
SCP or the file-transfer method already used for the proposal site.

## 2. Back up the current proposal

Run on the VM:

```bash
sudo cp -a /var/www/html "/var/www/html-proposal-backup-$(date +%Y%m%d-%H%M%S)"
```

This creates a separate copy; it does not remove the live website.

## 3. Install the application

```bash
sudo apt update
sudo apt install -y python3-venv python3-pip unzip
sudo mkdir -p /var/www/swapscholar
sudo unzip -o ~/swapscholar-vm-ready.zip -d /var/www/swapscholar
sudo python3 -m venv /var/www/swapscholar/venv
sudo /var/www/swapscholar/venv/bin/pip install -r /var/www/swapscholar/requirements.txt
sudo mkdir -p /var/www/swapscholar/instance
sudo chown -R www-data:www-data /var/www/swapscholar
```

## 4. Create production settings

Generate a secret:

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

Copy the example:

```bash
sudo cp /var/www/swapscholar/deploy/swapscholar.env.example /etc/swapscholar.env
sudo nano /etc/swapscholar.env
```

Replace the secret-key placeholder with the generated value. Keep:

```text
SWAPSCHOLAR_DATABASE=/var/www/swapscholar/instance/swapscholar.sqlite
SWAPSCHOLAR_SERVER_IP=20.46.113.242
SWAPSCHOLAR_COOKIE_SECURE=1
```

Protect the file:

```bash
sudo chown root:www-data /etc/swapscholar.env
sudo chmod 640 /etc/swapscholar.env
```

## 5. Initialise SQLite and optional demo data

```bash
sudo -u www-data env \
  SWAPSCHOLAR_DATABASE=/var/www/swapscholar/instance/swapscholar.sqlite \
  SWAPSCHOLAR_SECRET_KEY=temporary-initialisation-key \
  /var/www/swapscholar/venv/bin/flask --app /var/www/swapscholar/app.py init-db
```

For the assignment demonstration, add sample accounts:

```bash
sudo -u www-data env \
  SWAPSCHOLAR_DATABASE=/var/www/swapscholar/instance/swapscholar.sqlite \
  SWAPSCHOLAR_SECRET_KEY=temporary-initialisation-key \
  /var/www/swapscholar/venv/bin/flask --app /var/www/swapscholar/app.py seed-demo
```

## 6. Start the application service

```bash
sudo cp /var/www/swapscholar/deploy/swapscholar.service /etc/systemd/system/swapscholar.service
sudo systemctl daemon-reload
sudo systemctl enable --now swapscholar
sudo systemctl status swapscholar --no-pager
```

Before changing Apache, confirm the private application responds:

```bash
curl -I http://127.0.0.1:8000/
```

Expected result: `HTTP/1.1 200 OK`.

## 7. Connect the existing Apache HTTPS site

Enable the required Apache modules:

```bash
sudo a2enmod proxy proxy_http headers
```

Open the current HTTPS VirtualHost created for
`swapscholar36018014.japaneast.cloudapp.azure.com` and add the directives from:

```text
/var/www/swapscholar/deploy/apache-reverse-proxy.conf
```

Do not remove the existing certificate paths or HTTPS settings. Test before
reloading:

```bash
sudo apache2ctl configtest
sudo systemctl reload apache2
```

## 8. Final checks

```bash
sudo systemctl is-active swapscholar
sudo systemctl is-active apache2
curl -I https://swapscholar36018014.japaneast.cloudapp.azure.com/
```

Then test in the browser:

1. Home and Browse Skills load over HTTPS.
2. Log in with `aisha@demo.swapscholar` / `Demo123!`.
3. Dashboard shows the seeded pending request.
4. Matches, profile, skills and statistics pages open.
5. Log out and register a fresh test account.

## Rollback

If the new app must be removed from the live URL, remove only the reverse-proxy
directives added to the existing HTTPS VirtualHost, run
`sudo apache2ctl configtest`, then reload Apache. The timestamped
`/var/www/html-proposal-backup-*` folder remains available.

Useful diagnostics:

```bash
sudo journalctl -u swapscholar -n 80 --no-pager
sudo tail -n 80 /var/log/apache2/error.log
```
