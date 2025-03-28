from openai import OpenAI
import logging
from time import sleep


def create_prompt(cell_content):
    """
    Creates a formatted prompt by combining the template with cell content.
    Args:
        cell_content (str): The content from the cell
    Returns:
        str: Combined prompt ready for GPT processing
    """
    # Custom prompt for GPT
    gpt_prompt = """
    Custom GPT Bot Email Template Instructions

    Objective: Generate initial cold emails for outreach, following the specific template provided below. Only modify the sections within brackets for personalization; all other content should remain fixed.

    Email Template:

    "[Name of the Person] - watched your episode about [Personalisation] on the [Name of Pod]. Honestly so good.

    We're Scale Brands Lab—an invite-only firm that helps investor-friendly organizations gain major media exposure.

    We specialize in working with real estate firms, by getting them featured on top media outlets for massive exposure. 

    It goes from instant recognition to people flocking to your next {any-one from the following - [Syndication/REIT/Multifamily deal]}, real fast.

    Without a shadow of a doubt, we can explode your material. There's so much value there.

    Would you like to get more info?"

    Example Email:

    "Jason - watched your episode about "starting the clock" on the Real Estate Today. Honestly so good.

    We're Scale Brands Lab—an invite-only firm that helps investor-friendly organizations gain major media exposure.

    We specialize in working with real estate firms, by getting them featured on top media outlets for massive exposure. 

    It goes from instant recognition to people flocking to your next Multifamily deal, real fast.

    Without a shadow of a doubt, we can explode your material. There's so much value there.

    Would you like to get more info?"

    Instructions:

    1. Personalization Fields:
    - Replace [Name of the Person] with the name of the person given in the prompt.
    - Replace [PERSONALISATION] with a short, specific comment about a particular insight or segment of the podcast content.
    - Replace [Name of Pod] with the podcast name given in the prompt. 
    - Select any-one of the following - [Syndication/REIT/Multifamily deal] for this line, deduce it from the Industry details. If what has to be selected cannot be deduced from the ICP Type or any other information in Industry Details, then choose according to other details.
    - While personalizing: Write the personalization in 3rd Grade level. The sentence should not be too long and complex. Use shorter sentences and simpler words.
 

    2. Fixed Content:
    - Do not change any other text in the template. All non-bracketed content should remain exactly as written, preserving the wording, tone, and format. Be very very strict on this, I don't want anything else apart from the bracketed  content to change. 

    3. Tone and Language:
    - Keep the tone friendly and professional.
    - Ensure the language is simple, conversational, and concise to stay within a ~150-word limit.

    4. Dont send anything else except for the Email
    """
    # gpt_prompt = """
    # Task: Fill the given keys of the form using an episode transcript and website content if any, if no information is available or cannot be deduced from the transcript, just pass NA 1.Sub-Industries (examples - Commercial Real Estate, Property Management Companies, Residential Real Estate Agents, Real Estate Developers, Etc) 2. Company Size 3. Location 4. Revenue 5. ICP Type options - ["NA", "Syndication", "REIT", "Multifamily"]
    # Topic: ICP classification for Real Estate Industry
    # Style: Business
    # Tone: Confident
    # Audience: Business audience
    # Output Format: Sub-Industries -
    #         2. Company Size - 
    #         3. Location - 
    #         4. Revenue - 
    #         5. ICP Type - 
    # """
    cleaned_content = str(cell_content).strip() if cell_content else ""
    full_prompt = f"{gpt_prompt.strip()}\n\n:\n{cleaned_content}"
    return full_prompt


def process_with_gpt(content, api_key, max_retries=3, delay=1):
    """Process content with GPT API with retry logic"""
    client = OpenAI(api_key=api_key)
    try:
        for attempt in range(max_retries):
            try:
                full_prompt = create_prompt(content)
                response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": "You are a helpful assistant that analyses content and helps in identifying what the real estate company is"},
                        {"role": "user", "content": full_prompt}
                    ],
                    temperature=0.7,
                    max_tokens=500
                )
                return response.choices[0].message.content.strip()
            except Exception as e:
                if "rate_limit" in str(e).lower() and attempt < max_retries - 1:
                    sleep_time = delay * (attempt + 1)
                    logging.warning(f"Rate limit reached. Retrying in {sleep_time} seconds...")
                    sleep(sleep_time)
                else:
                    raise        
    except Exception as e:
        logging.error(f"Failed to process content with GPT: {str(e)}")
        return f"Error: {str(e)}"