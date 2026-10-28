<div align="center">

# ⚖️ Nyaya-Dwarpal

**Speak your legal problem in your own language and get a plain-language answer grounded in Indian law.**

[![Live demo](https://img.shields.io/badge/Live%20demo-AWS%20Amplify-FF9900?style=flat-square)](https://main.d1y87jb5yrv6jl.amplifyapp.com/)
![Python 3.11](https://img.shields.io/badge/Python-3.11-3776AB?style=flat-square&logo=python&logoColor=white)
![AWS CDK](https://img.shields.io/badge/IaC-AWS%20CDK-232F3E?style=flat-square&logo=amazonaws&logoColor=white)
![Bedrock](https://img.shields.io/badge/AI-Amazon%20Nova%20Lite-232F3E?style=flat-square)
[![MIT License](https://img.shields.io/badge/License-MIT-blue?style=flat-square)](LICENSE)

[Live demo](https://main.d1y87jb5yrv6jl.amplifyapp.com/) · [Features](#features) · [Architecture](#architecture) · [Run it yourself](#run-it-yourself) · [API](#api)

</div>

---

## Why

Most Indians do not read legal English, a lawyer's first consultation costs more than many families can spare, and the new criminal codes (BNS and BNSS, 2023) replaced the IPC and CrPC sections people had heard of. Nyaya-Dwarpal ("gatekeeper of justice") is a first stop: describe the problem by voice or text in an Indian language, and it tells you what kind of legal issue it is, which sections may apply, and what to do next.

Built for the **AI for Bharat** hackathon on a serverless AWS stack.

## Features

| | Feature | What it does |
|---|---|---|
| 🎤 | **Voice Triage** | Record your problem in the browser (or type it). Sarvam AI's Saaras v3 model turns speech into text; Amazon Nova Lite on Bedrock then detects urgency and emotional state, classifies the issue (civil, criminal, consumer, family, property, …), lists relevant BNS sections in plain language and suggests next steps. |
| 📄 | **Document Verification** | Upload a PDF, Word or text document (a rental agreement, a job contract, a legal notice). The AI flags risky or missing clauses with **High / Medium / Low** severity. |
| 🌐 | **Document Translation** | Upload a `.txt` or `.pdf` in a regional language. AWS Textract reads it, Sarvam AI translates it to English, and a legal glossary keeps legal terms consistent. |
| 🗂️ | **Case History** | Every triage is saved to DynamoDB. Browse past cases with their category, sections and full transcript. |
| 🗣️ | **Indian languages** | The interface switches between English, Hindi, Telugu, Tamil, Bengali and Marathi. Typed input also accepts Gujarati, Kannada, Malayalam and Punjabi. |

**Work in progress:** the *Legal Library* page is a placeholder, and the *Generate Petition* button is not wired to the UI yet (the `petition_architect` Lambda behind `/petition/*` is deployed but unused by the frontend).

## Architecture

```mermaid
flowchart LR
    UI["Web app<br/>HTML + Tailwind + vanilla JS<br/>(AWS Amplify)"] --> APIGW["API Gateway<br/>(REST, prod stage)"]

    APIGW -->|POST /transcribe| AT["AudioTranscribe λ"]
    APIGW -->|POST /voice/triage| VT["VoiceTriage λ"]
    APIGW -->|POST /validate/document| DV["DocumentVerifier λ"]
    APIGW -->|POST /translate/document| DT["DocumentTranslation λ"]
    APIGW -->|GET /cases| CM["CaseMemory λ"]
    APIGW -->|POST /petition/*| PA["PetitionArchitect λ"]

    AT --> SARVAM["Sarvam AI<br/>Saaras v3 speech-to-text"]
    DT --> SARVAM
    DT --> TX["Amazon Textract<br/>(ap-south-1)"]
    VT --> BR["Amazon Bedrock<br/>Nova Lite (us-east-1)"]
    DV --> BR
    PA --> BR

    VT --> DDB[("DynamoDB<br/>sessions · documents · glossary")]
    CM --> DDB
    DT --> DDB
    DT --> S3[("S3<br/>documents · archive")]
```

The stack is deployed to **ap-south-2 (Hyderabad)** by default. Bedrock is called in `us-east-1` and Textract in `ap-south-1`, where those services are available.

## Tech stack

- **Frontend:** a single `ui/index.html` page with Tailwind CSS (CDN) and vanilla JavaScript, recording audio with the MediaRecorder API. Hosted on AWS Amplify (`amplify.yml` serves the `ui/` folder as is, with no build step).
- **Backend:** six Python 3.11 AWS Lambda functions behind API Gateway, sharing a Lambda layer (`lambda_functions/shared`) for the Bedrock client, AWS helpers and Pydantic models.
- **AI:** Amazon Bedrock with `amazon.nova-lite-v1:0` for reasoning, and Sarvam AI for Indic speech-to-text and translation.
- **Data:** DynamoDB, S3 (encrypted buckets) and Textract.
- **Infrastructure as code:** AWS CDK v2 (Python), in `infrastructure/nyaya_dwarpal_stack.py`.

## Run it yourself

### Prerequisites

- An AWS account with the AWS CLI configured (`aws configure`)
- [Amazon Bedrock model access](https://docs.aws.amazon.com/bedrock/latest/userguide/model-access.html) to **Amazon Nova Lite** in `us-east-1`
- A [Sarvam AI](https://www.sarvam.ai/) API key
- Python 3.11 and Node.js 18+ (for the CDK CLI)

### 1. Install

```bash
git clone https://github.com/ScaryPython100/NyayaDwarpal.git
cd NyayaDwarpal

python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
npm install            # installs the AWS CDK CLI locally
```

### 2. Bundle the Lambda dependencies

Lambda packages are built from local folders, so their libraries are installed next to the code (these folders are git-ignored):

```bash
pip install -r lambda_functions/shared/requirements.txt -t lambda_functions/shared/python \
  --platform manylinux2014_x86_64 --only-binary=:all: --python-version 3.11
pip install -r lambda_functions/audio_transcribe/requirements.txt -t lambda_functions/audio_transcribe/python
pip install -r lambda_functions/document_verifier/requirements.txt -t lambda_functions/document_verifier \
  --platform manylinux2014_x86_64 --only-binary=:all: --python-version 3.11
```

### 3. Set your keys

```bash
cp .env.example .env   # then put your Sarvam key in .env
set -a; source .env; set +a
```

| Variable | Needed for |
|---|---|
| `SARVAM_API_KEY` | Speech-to-text and document translation |

Bedrock and Textract use your AWS credentials, so they need no key.

Keys are passed to the Lambdas as environment variables at deploy time. Never commit `.env`.

### 4. Deploy

```bash
npx cdk bootstrap      # once per account and region
npx cdk deploy         # deploys to ap-south-2; add -c region=<region> to change it
```

The deploy prints the API Gateway URL. Put it in `API_ENDPOINT` near the top of the `<script>` in `ui/index.html`.

### 5. Open the app

Open `ui/index.html` in a browser, or serve the folder (for example `python3 -m http.server -d ui 8000`). To host it, connect the repo to AWS Amplify; `amplify.yml` is already set up.

### Tests

```bash
pytest tests/unit
```

The unit tests mock AWS, so they need no account or keys. `tests/` also has scripts that call a deployed API (`test_voice_triage.py`, `test_document_translator.py`, …); change their base URL to your own deployment first.

## API

Base URL: the `prod` stage URL printed by `cdk deploy`.

| Method | Path | Body / query | Returns |
|---|---|---|---|
| `POST` | `/transcribe` | `{ audio (base64), language_code }` | Transcribed text |
| `POST` | `/voice/triage` | `{ userId, transcribedText, language }` | Urgency, emotion, legal category, BNS sections, next steps |
| `POST` | `/validate/document` | `{ document (base64), fileType, fileName }` | Issues rated High / Medium / Low |
| `POST` | `/translate/document` | `{ userId, fileContent (base64), filename }` or `{ userId, s3Key }` | English translation |
| `GET` | `/cases` | `?userId=<id>&limit=<n>` | Saved cases |
| `POST` | `/petition/generate`, `/petition/clarify` | Petition details | Draft / clarifying questions (not used by the UI yet) |

## Project structure

```
NyayaDwarpal/
├── app.py                         # CDK entry point
├── cdk.json                       # CDK settings
├── infrastructure/
│   └── nyaya_dwarpal_stack.py     # S3, DynamoDB, IAM, Lambdas, API Gateway
├── lambda_functions/
│   ├── shared/                    # Lambda layer: Bedrock client, AWS helpers, models
│   │   └── python/                #   the copy the layer ships (kept identical; a test checks)
│   ├── audio_transcribe/          # Speech-to-text via Sarvam AI
│   ├── voice_triage/              # Urgency, classification and BNS sections via Bedrock
│   ├── document_verifier/         # Clause risk check (PDF, DOCX, TXT)
│   ├── document_translator/       # Textract + Sarvam translation + glossary
│   ├── case_memory/               # Case history from DynamoDB
│   └── petition_architect/        # Petition drafting (backend only)
├── ui/
│   └── index.html                 # The whole web app
├── tests/                         # Unit tests and API test scripts
├── docs/
│   ├── requirements.md            # Original hackathon requirements
│   └── design.md                  # Original design (broader than what was built)
├── amplify.yml                    # Amplify hosting config
├── requirements.txt               # CDK and dev dependencies
└── .env.example
```

## Disclaimer

Nyaya-Dwarpal gives general legal information produced by AI. It is not legal advice and can be wrong. For anything that matters, talk to a lawyer or your nearest [District Legal Services Authority](https://nalsa.gov.in/) (free legal aid).

## License

[MIT](LICENSE)
