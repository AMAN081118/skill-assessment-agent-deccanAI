# AI-Powered Skill Assessment & Personalized Learning Plan Agent

An AI agent that takes a **Job Description** and a **candidate's resume**, conversationally assesses real proficiency on each required skill, identifies gaps, and generates a **personalized learning plan** with curated resources and time estimates.

## Quick Start

### Prerequisites

- Python 3.10+
- Groq API Key (free at [console.groq.com](https://console.groq.com))
- Google Gemini API Key (free at [aistudio.google.com](https://aistudio.google.com))

### Setup

```bash
# Clone the repo
git clone https://github.com/YOUR_USERNAME/skill-assessment-agent.git
cd skill-assessment-agent

# Create virtual environment
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows

# Install dependencies
pip install -r requirements.txt

# Set up environment variables
cp .env.example .env
# Edit .env and add your API keys

# Run the app
streamlit run app/streamlit_app.py
```
