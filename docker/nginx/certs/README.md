# SSL Certificates Directory

This directory contains SSL certificates for HTTPS configuration.

## Development Environment (Self-Signed Certificate)

For local development and testing, use a self-signed certificate:

```bash
# Generate self-signed certificate (valid for 365 days)
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout nginx-selfsigned.key \
  -out nginx-selfsigned.crt \
  -subj "/C=CN/ST=Beijing/L=Beijing/O=DevMind/CN=localhost" \
  -addext "subjectAltName=DNS:localhost,DNS:*.localhost,IP:127.0.0.1"
```

**Generated files:**
- `nginx-selfsigned.crt` - Certificate file
- `nginx-selfsigned.key` - Private key file

**Browser Warning:**
Self-signed certificates will show security warnings in browsers. This is normal for development.

## Production Environment (Real Certificate)

For production deployment, use certificates from a trusted Certificate Authority:

### Option 1: Let's Encrypt (Free, Recommended)

Using Certbot:

```bash
# Install certbot
sudo apt-get install certbot

# Generate certificate
sudo certbot certonly --standalone -d yourdomain.com

# Copy certificates to this directory
sudo cp /etc/letsencrypt/live/yourdomain.com/fullchain.pem ./nginx-selfsigned.crt
sudo cp /etc/letsencrypt/live/yourdomain.com/privkey.pem ./nginx-selfsigned.key
```

**Auto-renewal:**
```bash
# Test renewal
sudo certbot renew --dry-run

# Setup auto-renewal (cron)
0 0 * * * certbot renew --quiet --post-hook "docker restart backend-nginx"
```

### Option 2: Commercial CA (e.g., DigiCert, GeoTrust)

1. Generate CSR (Certificate Signing Request):
   ```bash
   openssl req -new -newkey rsa:2048 -nodes \
     -keyout nginx-selfsigned.key \
     -out domain.csr \
     -subj "/C=CN/ST=Beijing/L=Beijing/O=YourCompany/CN=yourdomain.com"
   ```

2. Submit `domain.csr` to your CA provider

3. Download and save the issued certificate:
   ```bash
   # Save as nginx-selfsigned.crt
   cat your-certificate.crt intermediate.crt > nginx-selfsigned.crt
   ```

### Option 3: Nginx Proxy Manager (External)

If using external Nginx Proxy Manager:
- **External proxy handles HTTPS** (with real certificates)
- **Internal nginx uses HTTP only** (remove HTTPS config)
- Simpler internal configuration

```yaml
# docker-compose.yml - HTTP only mode
ports:
  - "${NGINX_HTTP_PORT:-10080}:80"
  # Remove HTTPS port mapping
```

## File Naming Convention

For consistency, rename your certificates to:
- `nginx-selfsigned.crt` - Certificate (development)
- `nginx-selfsigned.key` - Private key (development)

Or for production:
- `production.crt` - Production certificate
- `production.key` - Production private key

Update `docker/nginx/default.conf` accordingly:
```nginx
ssl_certificate /etc/nginx/certs/production.crt;
ssl_certificate_key /etc/nginx/certs/production.key;
```

## Security Notes

⚠️ **Certificate files are committed to version control for convenience.**

**Note:** These are self-signed certificates for development/testing.
For production, consider using Let's Encrypt or other trusted CA certificates.

## Certificate Validation

Test your certificate:

```bash
# Check certificate expiry
openssl x509 -in nginx-selfsigned.crt -noout -dates

# Verify certificate and key match
openssl x509 -noout -modulus -in nginx-selfsigned.crt | openssl md5
openssl rsa -noout -modulus -in nginx-selfsigned.key | openssl md5
# The two MD5 hashes should match
```

## Quick Start

### Development:
```bash
# Already generated (self-signed)
# Just start services
docker-compose -f docker-compose.dev.yml up -d
```

### Production:
```bash
# 1. Obtain real certificate (Let's Encrypt or CA)
# 2. Copy to this directory
# 3. Ensure files are named correctly
# 4. Restart nginx
docker restart backend-nginx
```
