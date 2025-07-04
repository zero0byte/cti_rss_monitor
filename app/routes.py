import os
import re
import json
import openai
import requests
from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from app.models import Settings, Prompt
from app import db

main = Blueprint('main', __name__)

def regex_extract_iocs(text):
    md5 = re.findall(r"\b[a-fA-F0-9]{32}\b", text)
    sha1 = re.findall(r"\b[a-fA-F0-9]{40}\b", text)
    sha256 = re.findall(r"\b[a-fA-F0-9]{64}\b", text)
    ips = re.findall(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", text)
    domains = re.findall(r"\b[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b", text)
    return {"md5": md5, "sha1": sha1, "sha256": sha256, "ips": ips, "domains": domains}

def call_openai(model, messages):
    settings = Settings.query.first()
    if not settings or not settings.openai_api_key:
        raise ValueError("OpenAI API key not configured")
    
    client = openai.OpenAI(api_key=settings.openai_api_key)
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0.2,
        max_tokens=500
    )
    return response.choices[0].message.content

def send_to_joplin(title, content):
    settings = Settings.query.first()
    if not settings or not settings.joplin_api_url or not settings.joplin_token:
        raise ValueError("Joplin API settings not configured")
    
    url = settings.joplin_api_url
    params = {"token": settings.joplin_token}
    
    data = {
        "title": title,
        "body": content,
        "source_url": "",
        "tags": ["cti", "openai"]
    }
    
    response = requests.post(url, params=params, json=data)
    return response.json()

@main.route('/')
def index():
    return render_template('index.html')

@main.route('/settings', methods=['GET', 'POST'])
def settings_page():
    settings = Settings.query.first()
    
    if request.method == 'POST':
        settings.openai_api_key = request.form.get('openai_api_key')
        settings.joplin_api_url = request.form.get('joplin_api_url')
        settings.joplin_token = request.form.get('joplin_token')
        settings.joplin_enabled = 'joplin_enabled' in request.form
        
        # Process max_article_age (convert to int, default to 0 if invalid)
        try:
            max_age = int(request.form.get('max_article_age', 0))
            settings.max_article_age = max(0, max_age)  # Ensure it's not negative
        except (ValueError, TypeError):
            settings.max_article_age = 0
        
        db.session.commit()
        flash('Settings updated successfully!', 'success')
        return redirect(url_for('main.settings_page'))
    
    return render_template('settings.html', settings=settings)

@main.route('/prompts', methods=['GET', 'POST'])
def prompts_page():
    filter_prompt = Prompt.query.filter_by(name='filter_prompt').first()
    parse_prompt = Prompt.query.filter_by(name='parse_prompt').first()
    
    if request.method == 'POST':
        filter_prompt.content = request.form.get('filter_prompt')
        filter_prompt.model = request.form.get('filter_model')
        
        parse_prompt.content = request.form.get('parse_prompt')
        parse_prompt.model = request.form.get('parse_model')
        
        db.session.commit()
        flash('Prompts updated successfully!', 'success')
        return redirect(url_for('main.prompts_page'))
    
    return render_template('prompts.html', filter_prompt=filter_prompt, parse_prompt=parse_prompt)

@main.route('/process', methods=['POST'])
def process():
    data = request.get_json()
    title = data.get('title', 'Untitled')
    content = data.get('content', '')
    
    filter_prompt = Prompt.query.filter_by(name='filter_prompt').first()
    parse_prompt = Prompt.query.filter_by(name='parse_prompt').first()
    
    if not filter_prompt or not parse_prompt:
        return jsonify({"status": "error", "message": "Prompts not configured"}), 500
    
    # Extract the first 3000 characters to limit input size
    truncated_content = content[:3000]
    
    # Prepare the message for OpenAI
    messages = [
        {"role": "system", "content": "You are a concise CTI analyst assistant."},
        {"role": "user", "content": f"{filter_prompt.content} Article: {truncated_content}"}
    ]
    
    try:
        # Call the filter model (usually GPT-3.5)
        result_filter = call_openai(filter_prompt.model, messages)
        
        # Extract IOCs using regex
        iocs_regex = regex_extract_iocs(content)
        
        # Check if we need to use the more powerful model
        if any(kw in result_filter.lower() for kw in ["threat_group", "ttp"]):
            messages = [
                {"role": "system", "content": "You are a concise CTI analyst assistant."},
                {"role": "user", "content": f"{parse_prompt.content} Article: {truncated_content}"}
            ]
            result_parse = call_openai(parse_prompt.model, messages)
            final_result = result_parse
        else:
            final_result = result_filter
        
        # Try to parse the result as JSON
        try:
            summary_data = json.loads(final_result)
        except json.JSONDecodeError:
            summary_data = {"summary": final_result, "tags": ["cti"], "iocs": iocs_regex}
        
        # Ensure IOCs are included
        if "iocs" not in summary_data:
            summary_data["iocs"] = iocs_regex
        
        # Add the title
        summary_data["title"] = title
        
        # Format the content for Joplin
        joplin_content = f"# {summary_data['title']}\n\n"
        joplin_content += f"## Summary\n{summary_data.get('summary', 'No summary available')}\n\n"
        
        joplin_content += "## IOCs\n"
        for k, v in summary_data['iocs'].items():
            if v:  # Only add if there are values
                joplin_content += f"- {k.upper()}: {', '.join(v)}\n"
        
        if summary_data.get("ttp"):
            joplin_content += f"\n## TTPs\n- {' '.join(summary_data['ttp'])}\n"
        
        if summary_data.get("threat_groups"):
            joplin_content += f"\n## Threat Groups\n- {' '.join(summary_data['threat_groups'])}\n"
        
        # Send to Joplin
        try:
            joplin_response = send_to_joplin(summary_data["title"], joplin_content)
            return jsonify({"status": "success", "joplin_response": joplin_response})
        except ValueError as e:
            return jsonify({"status": "error", "message": str(e)}), 500
        except Exception as e:
            return jsonify({"status": "error", "message": f"Error sending to Joplin: {str(e)}"}), 500
        
    except ValueError as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    except Exception as e:
        return jsonify({"status": "error", "message": f"Error processing content: {str(e)}"}), 500

@main.route('/usage', methods=['GET'])
def usage():
    settings = Settings.query.first()
    if not settings or not settings.openai_api_key:
        return jsonify({"status": "error", "message": "OpenAI API key not configured"}), 500
    
    try:
        # The new OpenAI client doesn't have a direct billing.usage method
        # Instead, we'll return a message explaining this limitation
        return jsonify({
            "status": "info", 
            "message": "Usage data is not available through the API in this version. Please check your OpenAI dashboard for usage information.",
            "dashboard_url": "https://platform.openai.com/usage"
        })
    except Exception as e:
        return jsonify({"status": "error", "message": f"Error retrieving usage data: {str(e)}"}), 500
