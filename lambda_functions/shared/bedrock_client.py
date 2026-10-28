"""
AWS Bedrock Integration Utility

This module provides a wrapper for AWS Bedrock API calls with error handling,
retry logic, and rate limiting for the Nyaya-Dwarpal AI Agent.
"""

import json
import time
import boto3
from typing import Dict, Any, Optional
from botocore.exceptions import ClientError


class BedrockClient:
    """
    Wrapper for AWS Bedrock with Claude 3.5 Sonnet model
    
    Features:
    - Automatic retry with exponential backoff
    - Error handling for throttling
    - Prompt template management
    """
    
    # AWS Bedrock model ID - using Claude 3.5 Sonnet
    MODEL_ID = "amazon.nova-lite-v1:0"
    
    def __init__(self, region: str = "us-east-1"):
        """
        Initialize AWS Bedrock client
        
        Args:
            region: AWS region for Bedrock service
        """
        self.region = region
        self.client = None
    
    def _ensure_client(self):
        """Lazily initialize Bedrock client when needed"""
        if self.client is None:
            print(f"[Bedrock] Initializing client in region: {self.region}")
            self.client = boto3.client(
                service_name='bedrock-runtime',
                region_name=self.region
            )
    
    def invoke_model(
        self,
        prompt: str,
        max_tokens: int = 2048,
        temperature: float = 0.7,
        system_prompt: Optional[str] = None,
        retry_attempts: int = 3,
    ) -> Dict[str, Any]:
        """
        Invoke AWS Bedrock Claude model with retry logic
        
        Args:
            prompt: User prompt for the model
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature (0.0 to 1.0)
            system_prompt: Optional system prompt for context
            retry_attempts: Number of retry attempts on failure
            
        Returns:
            Dict containing model response and metadata
            
        Raises:
            Exception: If all retry attempts fail
        """
        # Ensure Bedrock client is initialized (lazy initialization)
        self._ensure_client()
        
        print(f"[Bedrock] Invoking model with temperature={temperature}, max_tokens={max_tokens}")
        
        # Prepare messages for Claude
        messages = [
            {
                "role": "user",
                "content": prompt
            }
        ]
        
        # Build request body for Claude
        request_body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": messages
        }
        
        # Add system prompt if provided
        if system_prompt:
            request_body["system"] = system_prompt
            print(f"[Bedrock] System prompt: {system_prompt[:200]}...")
        
        print(f"[Bedrock] Sending request to {self.MODEL_ID}...")
        
        # Retry logic with exponential backoff
        for attempt in range(retry_attempts):
            try:
                response = self.client.invoke_model(
                    modelId=self.MODEL_ID,
                    body=json.dumps(request_body)
                )
                
                # Parse response
                response_body = json.loads(response['body'].read())
                
                print(f"[Bedrock] Response received. Stop reason: {response_body.get('stop_reason')}")
                
                # Extract text from response
                text_content = ""
                for content_block in response_body.get('content', []):
                    if content_block.get('type') == 'text':
                        text_content += content_block.get('text', '')
                
                return {
                    "text": text_content,
                    "stop_reason": response_body.get('stop_reason'),
                    "usage": {
                        "prompt_tokens": response_body.get('usage', {}).get('input_tokens', 0),
                        "completion_tokens": response_body.get('usage', {}).get('output_tokens', 0),
                        "total_tokens": response_body.get('usage', {}).get('input_tokens', 0) + response_body.get('usage', {}).get('output_tokens', 0)
                    },
                    "model_id": self.MODEL_ID,
                }
                
            except ClientError as e:
                error_code = e.response['Error']['Code']
                error_message = e.response['Error']['Message']
                print(f"[Bedrock] Error on attempt {attempt + 1}: {error_code} - {error_message}")
                
                # Handle throttling with exponential backoff
                if error_code == 'ThrottlingException' and attempt < retry_attempts - 1:
                    wait_time = (2 ** attempt) * 1.0  # 1s, 2s, 4s
                    print(f"[Bedrock] Throttled. Waiting {wait_time}s...")
                    time.sleep(wait_time)
                    continue
                
                # Handle temporary errors with retry
                if attempt < retry_attempts - 1:
                    print(f"[Bedrock] Retrying in 2s...")
                    time.sleep(2.0)
                    continue
                
                # Re-raise if last attempt
                raise
            
            except Exception as e:
                error_message = str(e)
                print(f"[Bedrock] Error on attempt {attempt + 1}: {error_message}")
                
                # Handle temporary errors with retry
                if attempt < retry_attempts - 1:
                    print(f"[Bedrock] Retrying in 2s...")
                    time.sleep(2.0)
                    continue
                
                # Re-raise if last attempt
                raise
        
        raise Exception("All retry attempts failed")
    
    def build_legal_triage_prompt(
        self,
        transcribed_text: str,
        language: str,
        use_native_script: bool = True,
    ) -> str:
        """
        Build prompt for legal problem triage and classification
        
        Args:
            transcribed_text: User's grievance in their native language
            language: Language code (e.g., 'en' for English, 'hi' for Hindi, 'ta' for Tamil)
            use_native_script: If True, use native script; if False, use romanized text
            
        Returns:
            Formatted prompt for Bedrock
        """
        # Language name mapping
        language_map = {
            'en': {'name': 'English', 'script': 'Latin script'},
            'hi': {'name': 'Hindi', 'script': 'Devanagari script (देवनागरी अक्षर)'},
            'te': {'name': 'Telugu', 'script': 'Telugu script (తెలుగు అక్షరాలు)'},
            'ta': {'name': 'Tamil', 'script': 'Tamil script (தமிழ் எழுத்துக்கள்)'},
            'bn': {'name': 'Bengali', 'script': 'Bengali script (বাংলা লিপি)'},
            'mr': {'name': 'Marathi', 'script': 'Devanagari script (देवनागरी अक्षर)'},
            'gu': {'name': 'Gujarati', 'script': 'Gujarati script (ગુજરાતી લિપિ)'},
            'kn': {'name': 'Kannada', 'script': 'Kannada script (ಕನ್ನಡ ಲಿಪಿ)'},
            'ml': {'name': 'Malayalam', 'script': 'Malayalam script (മലയാളം ലിപി)'},
            'pa': {'name': 'Punjabi', 'script': 'Gurmukhi script (ਗੁਰਮੁਖੀ ਲਿਪੀ)'},
        }
        
        lang_info = language_map.get(language, {'name': language, 'script': 'native script'})
        language_name = lang_info['name']
        script_name = lang_info['script']
        
        # Build language instruction based on language and script preference
        if language == 'en':
            # English - no native script confusion
            language_instruction = """Respond in clear, professional English.

JSON keys must be in English. All content values must be in English."""
            language_reminder = ""
        elif use_native_script:
            # Non-English with native script
            language_instruction = f"""YOU MUST RESPOND ONLY IN {language_name.upper()} USING {script_name.upper()}.

For {language_name}: Use ONLY {script_name}.

ABSOLUTELY NO English or Roman letters in your response content. JSON keys must stay in English but ALL values must be in {script_name}."""
            language_reminder = f"""

REMINDER: YOU MUST RESPOND ONLY IN {language_name.upper()} USING {script_name.upper()}. ABSOLUTELY NO English or Roman letters in response values."""
        else:
            # Non-English with romanized text
            language_instruction = f"""Respond in {language_name} using English/Roman letters (romanized/transliterated text).

JSON keys must be in English. All content values must be in romanized {language_name}."""
            language_reminder = ""
        
        return f"""{language_instruction}

You are an expert Indian lawyer with 20+ years of experience specializing in Bharatiya Nyaya Sanhita (BNS), Consumer Protection Act 2019, and Indian civil/criminal law. A client has come to you with this legal issue:

CLIENT'S ISSUE (in {language_name}):
"{transcribed_text}"

Your job is to provide EXTREMELY DETAILED, ACTIONABLE legal advice specific to Indian law that the client can act on IMMEDIATELY. Do NOT give generic advice like "consult a lawyer" - that's useless. Give SPECIFIC steps they can take TODAY.

CRITICAL INSTRUCTIONS FOR INDIAN LAW:
- ALWAYS identify specific BNS (Bharatiya Nyaya Sanhita) sections, NOT IPC
- For consumer issues, cite Consumer Protection Act 2019 sections
- For auto/taxi overcharging, cite Motor Vehicles Act 1988 + Consumer Protection Act 2019
- For property, cite Transfer of Property Act 1882, Registration Act 1908
- For employment, cite Payment of Wages Act 1936, Industrial Disputes Act 1947
- For family law, cite Hindu Marriage Act 1955, Special Marriage Act 1954
- DO NOT use "Other" category unless absolutely necessary

ANALYZE AND CATEGORIZE:

1. LEGAL CATEGORY (choose ONE most specific - DO NOT use "Other"):
   - Consumer Rights: defective products, service deficiency, overcharging, fraud by seller/service provider, auto/taxi fare disputes
   - Property Dispute: boundary disputes, illegal construction, encroachment, landlord-tenant issues, rent disputes
   - Criminal: theft, fraud, assault, cheating, criminal intimidation, domestic violence
   - Family Law: divorce, child custody, maintenance, domestic violence, dowry harassment
   - Labor Rights: unpaid wages, wrongful termination, workplace harassment, PF/ESI issues
   - Cyber Crime: online fraud, identity theft, cyberbullying, data breach

   EXAMPLES OF CORRECT CATEGORIZATION:
   - "Auto driver charged ₹500 for ₹200 ride" → Consumer Rights (NOT Other)
   - "Landlord not returning deposit" → Property Dispute (NOT Other)
   - "Boss hasn't paid salary for 2 months" → Labor Rights (NOT Other)
   - "Someone stole my phone" → Criminal (NOT Other)
   - "Husband is abusive" → Family Law (NOT Other)
   - "Fake product sold online" → Consumer Rights (NOT Other)

2. URGENCY LEVEL:
   - HIGH: Unpaid salary 2+ months, eviction notice, domestic violence, immediate threat, legal deadline within 30 days, arrest warrant
   - MEDIUM: Defective product, contract dispute, property maintenance, delayed payment, consumer complaint
   - LOW: General consultation, information request, minor disputes, preventive advice

3. IDENTIFY SPECIFIC INDIAN LAWS (MANDATORY):

   For CONSUMER RIGHTS (auto/taxi overcharging, defective products, service issues):
   - Consumer Protection Act 2019, Section 2(9) - defines "consumer"
   - Consumer Protection Act 2019, Section 35 - unfair trade practices
   - Motor Vehicles Act 1988, Section 67 - fare regulation for auto/taxi
   - File complaint at: District Consumer Forum (free for claims under ₹1 crore)

   For CRIMINAL matters:
   - Bharatiya Nyaya Sanhita (BNS) 2023 - replaced IPC
   - BNS Section 303 - theft (replaced IPC 378)
   - BNS Section 318 - cheating (replaced IPC 420)
   - BNS Section 115 - voluntarily causing hurt (replaced IPC 323)
   - BNS Section 351 - criminal intimidation (replaced IPC 506)
   - File FIR at: Nearest police station or online via state police portal

   For PROPERTY disputes:
   - Transfer of Property Act 1882
   - Registration Act 1908
   - Rent Control Acts (state-specific)
   - File suit at: Civil Court with jurisdiction

   For LABOR RIGHTS:
   - Payment of Wages Act 1936, Section 5 - timely payment
   - Industrial Disputes Act 1947
   - Employees' Provident Funds Act 1952
   - File complaint at: Labour Commissioner (free)

   For FAMILY LAW:
   - Hindu Marriage Act 1955 (for Hindus)
   - Special Marriage Act 1954 (for all religions)
   - Protection of Women from Domestic Violence Act 2005
   - File petition at: Family Court

4. PROVIDE EXTREMELY DETAILED ADVICE:

Your response MUST include:

A. IMMEDIATE ACTIONS (What to do in next 24-48 hours):
   - Specific documents to gather (with examples)
   - Evidence to collect (photos, recordings, witnesses)
   - People to contact (with phone numbers/websites if possible)

B. STEP-BY-STEP LEGAL PROCESS (Timeline-based):
   - DAY 1-3: First actions
   - WEEK 1: Legal notice/complaint filing
   - WEEK 2-4: Follow-up actions
   - MONTH 2+: Court proceedings if needed

C. WHERE TO FILE COMPLAINTS:
   - Exact office names (Labour Commissioner, Consumer Forum, Police Station, etc.)
   - Online portals (with URLs like shramsuvidha.gov.in, consumerhelpline.gov.in)
   - Physical addresses if known
   - Free vs paid options

D. COST BREAKDOWN:
   - Legal notice: ₹2,000-5,000
   - Court filing fees: ₹500-2,000
   - Lawyer fees: ₹10,000-50,000 (range based on complexity)
   - FREE options: Legal aid, government helplines, online complaints

E. TIMELINE:
   - Best case: X days/weeks
   - Average case: X months
   - Worst case: X months/years

F. LEGAL RIGHTS & LAWS:
   - Specific Act names (Payment of Wages Act 1936, Consumer Protection Act 2019, etc.)
   - Section numbers (Section 5, Section 35, etc.)
   - What the law says in simple language
   - Penalties for violator

G. COMPENSATION/REMEDY:
   - What client can claim (money, possession, injunction, etc.)
   - How much (specific amounts or formulas)
   - Interest rates (typically 9-15% per annum)

H. FREE RESOURCES:
   - State Legal Services Authority (free lawyers)
   - Government helplines (with numbers)
   - Online complaint portals
   - NGOs that can help

I. WARNINGS/CAUTIONS:
   - Time limits (statute of limitations)
   - Documents NOT to sign
   - Common mistakes to avoid
   - When to definitely hire a lawyer

CRITICAL INSTRUCTIONS:
- Your recommendation MUST be at least 500 words with specific, actionable steps
- DO NOT give generic advice like "consult a legal professional"
- Be as detailed as a real lawyer consultation
- Choose the MOST SPECIFIC category from the 6 options - NEVER use "Other"
- ALWAYS cite specific BNS sections (NOT IPC), Consumer Protection Act sections, or other Indian laws
- Return ONLY valid JSON - NO markdown backticks, NO preamble, NO extra text

EXAMPLE FOR AUTO DRIVER OVERCHARGING:
If client says "Auto driver charged me ₹500 for a ₹200 ride", you MUST respond:
{{
  "category": "Consumer Rights",
  "subCategory": "Auto fare overcharging",
  "legalSections": [
    {{
      "act": "Consumer Protection Act, 2019",
      "section": "Section 2(9)",
      "description": "Defines 'consumer' - any person who hires services for consideration",
      "penalty": "Compensation + punitive damages up to ₹1 lakh",
      "remedy": "Full refund of excess amount + compensation for harassment"
    }},
    {{
      "act": "Motor Vehicles Act, 1988",
      "section": "Section 67",
      "description": "Regulates fares for auto-rickshaws and taxis",
      "penalty": "Fine up to ₹500 for first offense, ₹1,500 for subsequent",
      "remedy": "Report to RTO, file consumer complaint for refund"
    }}
  ],
  "recommendation": "IMMEDIATE ACTION: You have been overcharged by an auto driver, which violates both Consumer Protection Act 2019 and Motor Vehicles Act 1988.\\n\\nSTEP 1 (TODAY): Take photo of auto meter reading, note auto registration number, save payment receipt/UPI screenshot.\\n\\nSTEP 2 (DAY 1-2): File online complaint at:\\n- National Consumer Helpline: 1800-11-4000 or consumerhelpline.gov.in\\n- State Transport Authority: [your state] RTO website\\n- Consumer Forum: edaakhil.nic.in (for claims under ₹50 lakhs)\\n\\nSTEP 3 (WEEK 1): If no response, file written complaint at District Consumer Forum (COMPLETELY FREE for claims under ₹1 crore). Required documents: Auto receipt, meter photo, complaint letter.\\n\\nLEGAL BASIS:\\nUnder Consumer Protection Act 2019, Section 2(9), you are a 'consumer' who hired auto services. Section 35 covers unfair trade practices including overcharging. Under Motor Vehicles Act 1988, Section 67, auto fares are regulated by state government - charging more is illegal.\\n\\nYOUR RIGHTS:\\n1. Full refund of excess ₹300\\n2. Compensation for mental harassment (₹2,000-5,000)\\n3. Punitive damages if fraud proven (up to ₹1 lakh)\\n\\nWHERE TO FILE:\\n1. Consumer Forum (BEST option): District Consumer Forum, [your district]. File online at edaakhil.nic.in. COMPLETELY FREE. No lawyer needed for claims under ₹10 lakhs.\\n2. RTO Complaint: [Your state] Regional Transport Office. Online portal: [state].parivahan.gov.in\\n3. Police Complaint: If driver was abusive/threatening, file FIR under BNS Section 351 (criminal intimidation)\\n\\nCOSTS:\\n- Consumer Forum filing: FREE\\n- RTO complaint: FREE\\n- Lawyer (optional): ₹2,000-5,000 for simple cases\\n- Legal aid: FREE via District Legal Services Authority for income under ₹5 lakhs/year\\n\\nTIMELINE:\\n- Consumer Forum: 3-6 months for decision\\n- RTO action: 15-30 days for penalty on driver\\n- Mediation: 1-2 months (faster option)\\n\\nCOMPENSATION YOU CAN CLAIM:\\n- Excess fare: ₹300\\n- Interest: 9% per annum from date of incident\\n- Compensation: ₹2,000-5,000 for harassment\\n- Legal costs: ₹1,000-2,000 if you hire lawyer\\n\\nFREE RESOURCES:\\n1. National Consumer Helpline: 1800-11-4000 (free advice)\\n2. District Legal Services Authority: Free lawyer for income under ₹5 lakhs/year\\n3. Consumer Forum online filing: edaakhil.nic.in (no fees)\\n4. State Transport Helpline: [your state number]\\n\\nWARNINGS:\\n- File within 2 years of incident (limitation period)\\n- Keep all evidence safe (photos, receipts, witnesses)\\n- Don't accept verbal settlement without written agreement\\n- If driver threatens you, immediately file police complaint",
  "nextSteps": [
    "TODAY: Take photo of auto meter, note registration number, save payment receipt",
    "DAY 1: File online complaint at consumerhelpline.gov.in (takes 10 minutes)",
    "DAY 2: File complaint at state RTO website against auto driver",
    "DAY 7: If no response, visit District Consumer Forum with documents",
    "DAY 14: File written complaint at Consumer Forum (FREE, no lawyer needed)",
    "MONTH 1: Attend Consumer Forum hearing with evidence",
    "MONTH 3-6: Receive Consumer Forum order with compensation"
  ],
  "estimatedCost": "Consumer Forum: COMPLETELY FREE (no filing fees, no lawyer needed for simple cases). Optional lawyer: ₹2,000-5,000. Legal aid: FREE via District Legal Services Authority if annual income under ₹5 lakhs",
  "timeline": "RTO action: 15-30 days. Consumer Forum decision: 3-6 months. Mediation (faster): 1-2 months"
}}

Respond in JSON format with these EXACT keys:
{{
  "category": "Consumer Rights",
  "subCategory": "Service deficiency - overcharging",
  "urgency": "medium",
  "urgencyReason": "Consumer complaint should be filed within 2 years. While not immediately urgent, prompt action ensures better evidence preservation and faster resolution",
  "emotionalState": "frustrated",
  "facts": {{
    "who": "consumer and service provider (auto driver, shop owner, etc.)",
    "what": "overcharging, defective product, poor service",
    "when": "date of incident",
    "where": "location of incident",
    "amount": "monetary value involved"
  }},
  "legalSections": [
    {{
      "act": "Consumer Protection Act, 2019",
      "section": "Section 2(9)",
      "description": "Defines 'consumer' as any person who hires services or buys goods for consideration",
      "penalty": "Compensation + punitive damages as determined by Consumer Forum",
      "remedy": "Full refund + compensation for deficiency in service + mental harassment"
    }},
    {{
      "act": "Consumer Protection Act, 2019",
      "section": "Section 35",
      "description": "Covers unfair trade practices including overcharging, false representation, defective goods",
      "penalty": "Imprisonment up to 2 years + fine up to ₹10 lakhs for repeat offenders",
      "remedy": "Replacement of goods, refund of price, compensation for loss"
    }}
  ],
  "recommendation": "EXTREMELY DETAILED multi-paragraph advice with specific steps, timelines, costs, and resources. Include:\\n\\n1. IMMEDIATE ACTIONS (Next 24-48 hours):\\n- Gather receipts, bills, payment proof (UPI screenshots, bank statements)\\n- Take photos/videos of defective product or service issue\\n- Note down names, dates, locations, registration numbers\\n- Collect witness contact information if available\\n\\n2. LEGAL PROCESS (Week by week):\\n- DAY 1-3: File online complaint at National Consumer Helpline (1800-11-4000) or consumerhelpline.gov.in\\n- WEEK 1: Send legal notice to service provider via registered post (₹500-2,000 via lawyer or self-drafted)\\n- WEEK 2: If no response, file complaint at District Consumer Forum via edaakhil.nic.in (COMPLETELY FREE)\\n- WEEK 3-4: Attend first hearing at Consumer Forum with all documents\\n- MONTH 2-6: Consumer Forum passes order with compensation\\n\\n3. WHERE TO GO:\\n- District Consumer Forum: [Your district name] Consumer Forum. File online at edaakhil.nic.in or visit in person\\n- National Consumer Helpline: Call 1800-11-4000 for free guidance\\n- State Consumer Commission: For claims ₹1 crore to ₹10 crores\\n- National Consumer Commission: For claims above ₹10 crores\\n- Legal Aid: District Legal Services Authority for free lawyer (if income under ₹5 lakhs/year)\\n\\n4. YOUR RIGHTS UNDER CONSUMER PROTECTION ACT 2019:\\n- Section 2(9): You are a 'consumer' entitled to protection\\n- Section 35: Unfair trade practices are punishable\\n- Section 84: Consumer Forum can order refund + compensation + punitive damages\\n- Right to be heard, right to seek redressal, right to consumer education\\n\\n5. COSTS:\\n- Consumer Forum filing: COMPLETELY FREE (no court fees for any claim amount)\\n- Legal notice: ₹500-2,000 (optional, can self-draft)\\n- Lawyer fees: ₹2,000-10,000 (optional for simple cases, mandatory for complex cases)\\n- FREE legal aid: Available via District Legal Services Authority if annual income under ₹5 lakhs\\n- Mediation: FREE option available at Consumer Forum (faster resolution)\\n\\n6. TIMELINE:\\n- Online complaint response: 7-15 days\\n- Legal notice response: 15-30 days\\n- Consumer Forum decision: 3-6 months (simple cases), 6-12 months (complex cases)\\n- Mediation settlement: 1-2 months (fastest option)\\n- Appeal to State Commission: 6-12 months\\n- Appeal to National Commission: 1-2 years\\n\\n7. COMPENSATION YOU CAN CLAIM:\\n- Full refund of amount paid\\n- Replacement of defective goods\\n- Interest at 9-12% per annum from date of payment\\n- Compensation for mental harassment: ₹5,000-50,000 depending on severity\\n- Litigation costs: ₹2,000-10,000\\n- Punitive damages: Up to ₹1 lakh for deliberate fraud\\n\\n8. FREE RESOURCES:\\n- National Consumer Helpline: 1800-11-4000 (free advice, complaint filing)\\n- Consumer Forum online portal: edaakhil.nic.in (file complaint in 15 minutes)\\n- District Legal Services Authority: Free lawyer for income under ₹5 lakhs/year. Visit district court or call 15100\\n- State Consumer Helpline: [Your state] consumer helpline number\\n- Consumer awareness websites: consumerhelpline.gov.in, confonet.nic.in\\n\\n9. WARNINGS/CAUTIONS:\\n- File complaint within 2 years of cause of action (limitation period under Consumer Protection Act)\\n- Keep all original documents safe - submit only photocopies to Consumer Forum\\n- Don't accept verbal settlement - get written agreement on company letterhead\\n- If service provider offers replacement, ensure written guarantee\\n- For claims above ₹10 lakhs, consider hiring experienced consumer lawyer\\n- Attend all hearings - absence may lead to dismissal of complaint\\n- If you win, service provider may appeal - be prepared for longer process\\n\\n10. SPECIFIC TO YOUR CASE:\\n[Analyze the specific facts and provide tailored advice based on whether it's auto overcharging, defective product, poor service, etc.]",
  "nextSteps": [
    "TODAY: Collect all receipts, bills, payment proof, photos of defective product/service",
    "DAY 1: File online complaint at consumerhelpline.gov.in (takes 10 minutes, completely free)",
    "DAY 2: Send legal notice to service provider via registered post demanding refund/replacement within 15 days",
    "DAY 7: If no response, visit District Legal Services Authority for free lawyer consultation",
    "DAY 14: File written complaint at District Consumer Forum via edaakhil.nic.in (completely free, no lawyer needed)",
    "DAY 30: Attend first hearing at Consumer Forum with all original documents and 3 photocopies",
    "MONTH 2: Attend mediation session if offered by Consumer Forum (faster resolution)",
    "MONTH 3-6: Receive Consumer Forum order with compensation and refund"
  ],
  "requiredDocuments": [
    "Original bill/receipt/invoice of purchase or service",
    "Payment proof: UPI screenshot, bank statement, credit card statement, cash receipt",
    "Photos/videos of defective product or poor service",
    "Warranty card or guarantee certificate (if applicable)",
    "Correspondence with service provider: emails, WhatsApp chats, letters",
    "Witness statements (if any)",
    "Medical bills (if product/service caused injury)",
    "Identity proof: Aadhaar card, PAN card, Voter ID",
    "Address proof: Aadhaar, utility bill, rent agreement"
  ],
  "estimatedCost": "Consumer Forum filing: COMPLETELY FREE (no court fees). Legal notice: ₹500-2,000 (optional). Lawyer fees: ₹2,000-10,000 (optional for simple cases). Legal aid: FREE via District Legal Services Authority for income under ₹5 lakhs/year. Total out-of-pocket: ₹0-5,000 for most cases",
  "timeline": "Online complaint response: 7-15 days. Consumer Forum decision: 3-6 months (simple cases), 6-12 months (complex). Mediation: 1-2 months (fastest). Appeal to State Commission: 6-12 months. Appeal to National Commission: 1-2 years",
  "severity": "medium",
  "resources": [
    {{
      "name": "District Consumer Forum",
      "action": "File complaint online at edaakhil.nic.in or visit in person at [your district] Consumer Forum",
      "cost": "Completely FREE - no filing fees, no court fees, no lawyer needed for simple cases",
      "timeline": "Decision in 3-6 months for simple cases"
    }},
    {{
      "name": "National Consumer Helpline",
      "action": "Call 1800-11-4000 or visit consumerhelpline.gov.in for free advice and complaint filing",
      "cost": "Completely FREE helpline and online complaint system",
      "timeline": "Response within 7-15 days"
    }},
    {{
      "name": "District Legal Services Authority",
      "action": "Get free lawyer for income under ₹5 lakhs/year. Visit district court legal aid office or call 15100",
      "cost": "Completely FREE legal representation for eligible persons",
      "timeline": "Lawyer assigned within 7-15 days"
    }},
    {{
      "name": "State Consumer Commission",
      "action": "For claims ₹1 crore to ₹10 crores. File at state capital Consumer Commission",
      "cost": "FREE filing, but lawyer recommended for high-value claims",
      "timeline": "Decision in 6-12 months"
    }}
  ],
  "legalDisclaimer": "This advice is AI-generated for informational purposes only. Please consult a qualified legal professional before taking any action. Laws may vary by state."
}}
{language_reminder}"""
    
    def build_petition_generation_prompt(
        self,
        facts: Dict[str, Any],
        legal_category: str,
        relevant_sections: list,
    ) -> str:
        """
        Build prompt for structured petition generation
        
        Args:
            facts: Extracted facts from triage
            legal_category: Legal category (Civil, Criminal, etc.)
            relevant_sections: List of relevant legal sections
            
        Returns:
            Formatted prompt for Bedrock
        """
        return f"""You are a legal document drafting assistant for Indian courts. Generate a structured legal petition.

Facts: {json.dumps(facts, indent=2, ensure_ascii=False)}
Legal Category: {legal_category}
Relevant Sections: {', '.join(relevant_sections)}

Generate a petition with three sections:

1. FACTS: Organize the story chronologically with dates and parties clearly identified
2. GROUNDS: Cite relevant legal provisions (BNS/BNSS/CPC sections) that support the case
3. PRAYER: Specify the relief sought (monetary compensation, injunction, possession, etc.)

Ensure all procedural technicalities are met:
- Proper formatting with numbered paragraphs
- Required clauses and legal language
- Verification statement at the end

Format your response as JSON with keys: facts_section, grounds_section, prayer_section."""
    
    def build_citation_verification_prompt(
        self,
        petition_text: str,
        citations: list,
    ) -> str:
        """
        Build prompt for citation verification and relevance assessment
        
        Args:
            petition_text: Full petition text
            citations: List of extracted citations
            
        Returns:
            Formatted prompt for Bedrock
        """
        return f"""You are a legal citation verification assistant for Indian law. Review the following citations.

Petition excerpt:
{petition_text[:1000]}...

Citations to verify:
{json.dumps(citations, indent=2, ensure_ascii=False)}

For each citation:
1. Check if it's outdated (e.g., IPC instead of BNS, CrPC instead of BNSS)
2. Assess relevance to the legal argument
3. Suggest updated equivalents if outdated

Format your response as JSON array with objects containing: citation, is_outdated, suggested_replacement, relevance_score (0-1), relevance_explanation."""
    
    def build_clarification_prompt(
        self,
        petition_draft: str,
        missing_info: list,
    ) -> str:
        """
        Build prompt for generating clarifying questions
        
        Args:
            petition_draft: Current petition draft
            missing_info: List of missing information items
            
        Returns:
            Formatted prompt for Bedrock
        """
        return f"""You are a helpful legal assistant. The petition draft is missing some information.

Current draft:
{petition_draft[:500]}...

Missing information:
{json.dumps(missing_info, indent=2, ensure_ascii=False)}

Generate up to 5 targeted clarifying questions in simple, non-legal language. Focus on critical information like dates, amounts, and names.

Format your response as JSON array of strings (questions)."""
