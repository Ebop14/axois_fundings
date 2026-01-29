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
pip install -r requirements.txt
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

### 3. xAI API Key

1. Get an API key from [xAI](https://x.ai/)
2. Add it to your config file (see below)

### 4. Configuration

```bash
cp config/config.example.yaml config/config.yaml
```

Edit `config/config.yaml` with your settings:

```yaml
grok:
  api_key: "your-xai-api-key-here"
  model: "grok-3"

gmail:
  credentials_file: "credentials/credentials.json"
  token_file: "credentials/token.json"
  sender_filter: "axios.com"
  processed_label: "Axios-Processed"

smtp:
  timeout: 10
  rate_limit_delay: 2.0

email:
  subject_template: "Congrats on the {funding_amount} raise, {founder_first_name}!"
  sender_name: "Your Name"
```

### 5. First Run

On first run, a browser window will open for Gmail OAuth consent. Grant the requested permissions.

## Usage

```bash
# Process new newsletter emails and create drafts
python -m src.main

# Process with verbose logging
python -m src.main --verbose

# Dry run (show what would be done without creating drafts)
python -m src.main --dry-run

# Process specific number of emails
python -m src.main --max-emails 5

# Use custom config file
python -m src.main --config path/to/config.yaml
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
├── config/
│   └── config.example.yaml
├── credentials/          # OAuth tokens (gitignored)
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
- Check the `sender_filter` in config matches Axios sender
- Ensure emails are unread and not already labeled

### SMTP Verification Fails
- Some mail servers block verification attempts
- Increase `timeout` in config
- Try from a different network

## License

MIT
