from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List
from bson import ObjectId
from utils.db import MongoDB

router = APIRouter(
    prefix="/outreach",
    tags=["Outreach Campaigns"],
    responses={404: {"description": "Not found"}},
)

# --- Helper ---
def get_database():
    db = MongoDB.get_db()
    if db is None:
        raise HTTPException(status_code=500, detail="Database connection error")
    return db

# --- Models ---
class CampaignRequest(BaseModel):
    sheet_id: str
    agency_id: str

class TemplateEditRequest(BaseModel):
    campaign_id: str
    new_template_text: str
    new_template_output: str

class PromptModel(BaseModel):
    name: str
    use_case: str
    description: Optional[str]
    instructions: str
    tags: Optional[List[str]] = []

class TemplateModel(BaseModel):
    name: str
    template_text: str
    example_template_output: str
    prompt_id: str
    agency_id: Optional[str] = None
    is_default: bool = False

class FinalizeCampaignRequest(BaseModel):
    campaign_id: str
    campaign_name: str
    new_template_name: str
    new_template_text: str
    new_template_output: str

# --- API to fetch or create campaign ---
@router.post("/campaign/fetch")
def get_or_create_campaign(request: CampaignRequest):
    db = get_database()

    campaign = db.outreach_campaigns.find_one({"sheet_id": request.sheet_id})
    if campaign:
        campaign["_id"] = str(campaign["_id"])
        campaign["prompt_id"] = str(campaign["prompt_id"])
        campaign["template_id"] = str(campaign["template_id"])
        return {"campaign": campaign}

    default_prompt = db.email_prompts.find_one({"is_default": True})
    default_template = db.templates.find_one({"is_default": True})

    if not default_prompt or not default_template:
        raise HTTPException(status_code=500, detail="Default prompt or template not found")

    now = datetime.now()
    new_campaign = {
        "name": "Campaign 1 Default",
        "sheet_id": request.sheet_id,
        "agency_id": request.agency_id,
        "prompt_id": default_prompt["_id"],
        "template_id": default_template["_id"],
        "status": "draft",
        "created_at": now,
        "updated_at": now
    }

    result = db.outreach_campaigns.insert_one(new_campaign)
    new_campaign["_id"] = str(result.inserted_id)
    new_campaign["prompt_id"] = str(default_prompt["_id"])
    new_campaign["template_id"] = str(default_template["_id"])

    return {"campaign": new_campaign}

# --- API to update template in a campaign ---
@router.post("/campaign/update-template")
def update_campaign_template(request: TemplateEditRequest):
    db = get_database()
    campaign = db.outreach_campaigns.find_one({"_id": ObjectId(request.campaign_id)})

    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    if campaign.get("status") != "draft":
        raise HTTPException(status_code=400, detail="Template editing not allowed after outreach has started")

    # Clone new template
    old_template = db.templates.find_one({"_id": campaign["template_id"]})
    if not old_template:
        raise HTTPException(status_code=500, detail="Original template not found")

    now = datetime.now()
    new_template = {
        "name": "User Custom Template",
        "template_text": request.new_template_text,
        "example_template_output": request.new_template_output,
        "prompt_id": old_template["prompt_id"],
        "agency_id": old_template.get("agency_id"),
        "is_default": False,
        "created_at": now,
        "updated_at": now
    }
    result = db.templates.insert_one(new_template)

    # Update campaign
    db.outreach_campaigns.update_one(
        {"_id": ObjectId(request.campaign_id)},
        {"$set": {"template_id": result.inserted_id, "updated_at": now}}
    )

    return {"success": True, "new_template_id": str(result.inserted_id)}

# --- Create Prompt ---
@router.post("/prompt")
def create_prompt(prompt: PromptModel):
    db = get_database()
    prompt_doc = prompt.model_dump()
    prompt_doc.update({"created_at": datetime.now(), "updated_at": datetime.now(), "is_default": True})
    result = db.email_prompts.insert_one(prompt_doc)
    return {"_id": str(result.inserted_id)}

# --- Create Template ---
@router.post("/template")
def create_template(template: TemplateModel):
    db = get_database()
    template_doc = template.model_dump()
    template_doc.update({"created_at": datetime.now(), "updated_at": datetime.now()})
    result = db.templates.insert_one(template_doc)
    return {"_id": str(result.inserted_id)}

# --- Get All Prompts ---
@router.get("/prompt/all")
def get_all_prompts():
    db = get_database()
    prompts = list(db.email_prompts.find({}))
    for p in prompts:
        p["_id"] = str(p["_id"])
    return {"prompts": prompts}

# --- Get Templates for Prompt ---
@router.get("/template/by-prompt/{prompt_id}")
def get_templates_by_prompt(prompt_id: str):
    db = get_database()
    templates = list(db.templates.find({"prompt_id": str(prompt_id)}))
    for t in templates:
        t["_id"] = str(t["_id"])
    return {"templates": templates}

# --- API to finalize campaign and template ---
@router.post("/campaign/finalize")
def finalize_and_start_campaign(request: FinalizeCampaignRequest):
    db = get_database()
    campaign = db.outreach_campaigns.find_one({"_id": ObjectId(request.campaign_id)})

    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    if campaign.get("status") != "draft":
        raise HTTPException(status_code=400, detail="Only campaigns in draft status can be finalized")

    # Get original template
    old_template = db.templates.find_one({"_id": campaign["template_id"]})
    if not old_template:
        raise HTTPException(status_code=500, detail="Original template not found")

    now = datetime.now()
    # Clone template with custom name and content
    new_template = {
        "name": request.new_template_name,
        "template_text": request.new_template_text,
        "example_template_output": request.new_template_output,
        "prompt_id": old_template["prompt_id"],
        "agency_id": old_template.get("agency_id"),
        "is_default": False,
        "created_at": now,
        "updated_at": now
    }
    result = db.templates.insert_one(new_template)

    # Update campaign with final template, name, and status
    db.outreach_campaigns.update_one(
        {"_id": ObjectId(request.campaign_id)},
        {
            "$set": {
                "template_id": result.inserted_id,
                "campaign_name": request.campaign_name,
                "status": "running",
                "updated_at": now
            }
        }
    )

    db.agency_sheets.update_one(
        {"sheet_id": str(campaign["sheet_id"])},
        {
            "$set": {
                "status": "OUTREACH_STARTED",
                "updated_at": now
            }
        }
    )

    return {
        "success": True,
        "new_template_id": str(result.inserted_id),
        "status": "running",
        "campaign_name": request.campaign_name
    }

