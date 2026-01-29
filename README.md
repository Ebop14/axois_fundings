# Newsletter Outreach Automation Tool

A Python CLI tool that processes Axios Pro Rata newsletter emails, extracts company/funding info using Grok-3, discovers founder emails via SMTP verification, and creates personalized sales outreach drafts in Gmail.

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Gmail API      │────▶│  Grok-3 API     │────▶│  SMTP Verifier  │
│  (fetch emails) │     │  (extract info) │     │  (find emails)  │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                                                        │
                                                        ▼
                                               ┌─────────────────┐
                                               │  Gmail API      │
                                               │  (create draft) │
                                               └─────────────────┘
```

## Setup

### 1. Install Dependencies

```bash
pip3 install -r requirements.txt
```

### 2. Google Cloud Setup

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing
3. Enable the Gmail API:
   - Navigate to "APIs & Services" > "Library"
   - Search for "Gmail API" and enable it
4. Create OAuth2 credentials:
   - Go to "APIs & Services" > "Credentials"
   - Click "Create Credentials" > "OAuth client ID"
   - Select "Desktop app" as application type
   - Download the JSON file
5. Save the downloaded file as `credentials/credentials.json`

### 3. Environment Configuration

```bash
cp .env.example .env
```

Edit `.env` with your settings:

```bash
# xAI Grok-3 API settings
GROK_API_KEY=your-xai-api-key-here
GROK_MODEL=grok-3
GROK_BASE_URL=https://api.x.ai/v1

# Gmail settings
GMAIL_CREDENTIALS_FILE=credentials/credentials.json
GMAIL_TOKEN_FILE=credentials/token.json
GMAIL_SENDER_FILTER=axios.com
GMAIL_PROCESSED_LABEL=Axios-Processed

# SMTP verification settings
SMTP_TIMEOUT=10
SMTP_RATE_LIMIT_DELAY=2.0
SMTP_FROM_EMAIL=verify@example.com

# Email template settings
EMAIL_SUBJECT_TEMPLATE=Congrats on the {funding_amount} raise, {founder_first_name}!
EMAIL_SENDER_NAME=Your Name

# Logging
LOG_LEVEL=INFO
LOG_FILE=axios_fundings.log
```

### 4. First Run

On first run, a browser window will open for Gmail OAuth consent. Grant the requested permissions.

## Usage

```bash
# Process new newsletter emails and create drafts
python3 -m src.main

# Process with verbose logging
python3 -m src.main --verbose

# Dry run (show what would be done without creating drafts)
python3 -m src.main --dry-run

# Process specific number of emails
python3 -m src.main --max-emails 5
```

## How It Works

1. **Fetch Emails**: Connects to Gmail and fetches unread Axios Pro Rata emails that haven't been processed
2. **Extract Data**: Sends newsletter content to Grok-3 API to extract:
   - Company name
   - Funding amount
   - Investors
   - Founder names
   - Company domain
3. **Find Emails**: For each founder:
   - Generates email permutations (john@company.com, j.smith@company.com, etc.)
   - Verifies emails via SMTP handshake
   - Detects catch-all domains
4. **Create Drafts**: Generates personalized outreach emails and saves as Gmail drafts
5. **Mark Processed**: Labels emails to avoid reprocessing

## Project Structure

```
axios_fundings/
├── src/
│   ├── __init__.py
│   ├── main.py           # CLI entry point
│   ├── gmail_client.py   # Gmail API wrapper
│   ├── parser.py         # Grok-3 newsletter extraction
│   ├── email_finder.py   # Email permutation + SMTP verification
│   └── drafter.py        # Email template/generation
├── credentials/          # OAuth tokens (gitignored)
├── .env.example          # Environment template
├── requirements.txt
├── setup.py
└── README.md
```

## Email Permutations

For a founder named "John Smith" at company.com, the following patterns are tested:

- john@company.com
- john.smith@company.com
- jsmith@company.com
- j.smith@company.com
- smith@company.com
- johnsmith@company.com
- smithjohn@company.com
- smith.john@company.com
- john_smith@company.com
- john-smith@company.com

## SMTP Verification

The tool performs SMTP verification:

1. Looks up MX records for the domain
2. Connects to mail server
3. Performs HELO → MAIL FROM → RCPT TO handshake
4. Interprets response codes (250 = valid, 550 = invalid)
5. Detects catch-all domains

Rate limiting is enforced to avoid blacklisting.

## Troubleshooting

### OAuth Errors
- Delete `credentials/token.json` and re-run to re-authenticate
- Ensure Gmail API is enabled in Google Cloud Console

### No Emails Found
- Check the `GMAIL_SENDER_FILTER` in .env matches Axios sender
- Ensure emails are unread and not already labeled

### SMTP Verification Fails
- Some mail servers block verification attempts
- Increase `SMTP_TIMEOUT` in .env
- Try from a different network

## License

MIT
