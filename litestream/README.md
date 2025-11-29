# Litestream Backup Setup

Continuous SQLite replication to Cloudflare R2 (~$1/month).

## Quick Start (5 minutes)

### 1. Install Litestream

```bash
# macOS
brew install litestream

# Linux
curl -L https://github.com/benbjohnson/litestream/releases/latest/download/litestream-linux-amd64.tar.gz | tar xz
sudo mv litestream /usr/local/bin/
```

### 2. Create Cloudflare R2 Bucket

1. Go to [Cloudflare Dashboard](https://dash.cloudflare.com/) → R2
2. Create bucket named `chora-backup`
3. Create API token (R2 → Manage R2 API Tokens):
   - Permission: Object Read & Write
   - Scope: Apply to specific bucket → `chora-backup`
4. Copy the Account ID, Access Key ID, and Secret Access Key

### 3. Configure Environment

Create `.env` in workspace root:

```bash
# Cloudflare R2 Configuration
R2_ACCOUNT_ID=your_account_id
R2_BUCKET=chora-backup
R2_ACCESS_KEY_ID=your_access_key
R2_SECRET_ACCESS_KEY=your_secret_key
```

### 4. Generate Config and Start

```bash
# Generate litestream.yml from template
just backup-setup

# Start continuous replication (foreground)
just backup-start

# Or run in background
just backup-start-bg
```

## Commands

| Command | Description |
|---------|-------------|
| `just backup-setup` | Generate litestream.yml from .env |
| `just backup-start` | Start litestream (foreground) |
| `just backup-start-bg` | Start litestream (background) |
| `just backup-stop` | Stop background litestream |
| `just backup-status` | Check replication status |
| `just backup-restore` | Restore from R2 |
| `just backup-local` | Use local filesystem backup (dev) |

## Cost Estimate

Cloudflare R2 pricing (as of 2024):
- Storage: $0.015/GB/month
- Class A ops (write): $4.50/million
- Class B ops (read): $0.36/million
- Egress: FREE

**Typical chora usage**: ~$1/month
- 1GB storage: $0.015
- 100k writes/month: $0.45
- 10k reads/month: $0.004

## Local Development

For testing without R2:

```bash
# Use local filesystem backup
just backup-local

# This backs up to ~/.chora/backups/
```

## Restore from Backup

```bash
# List available snapshots
just backup-snapshots

# Restore to default location
just backup-restore

# Restore to specific path
just backup-restore /path/to/restore.db
```

## Troubleshooting

### "no replicas configured"
Run `just backup-setup` to generate litestream.yml from template.

### "access denied" from R2
Check your API token has Object Read & Write permission for the bucket.

### Database locked
Stop any process using the database before starting litestream.
Litestream requires exclusive access to the WAL file.

## Architecture

```
┌─────────────────┐     ┌──────────────┐     ┌─────────────────┐
│  chora.db       │────▶│  Litestream  │────▶│  Cloudflare R2  │
│  (local)        │     │  (daemon)    │     │  (backup)       │
└─────────────────┘     └──────────────┘     └─────────────────┘
       │                      │                     │
       │                      │                     │
   SQLite WAL          Continuous sync         Snapshots +
   writes              every 10s               WAL archive
```

Litestream intercepts SQLite WAL (Write-Ahead Log) writes and continuously replicates them to R2. Point-in-time recovery is possible using snapshots + WAL replay.
