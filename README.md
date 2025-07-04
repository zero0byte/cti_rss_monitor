# CTI Monitor - RSS to Joplin Integration

![joplin](https://github.com/user-attachments/assets/53261e39-d80f-46f9-9b21-ad9ad4baa306)

This application monitors RSS feeds, processes articles using OpenAI's GPT models, and sends the results to Joplin. It provides a modern Flask UI for configuring API keys, managing feeds, customising prompts, and processing content.

## Features

- **Modern UI**: Clean, responsive interface for managing all aspects of the application
- **RSS Feed Monitoring**: Built-in RSS feed monitoring with customisable check intervals
- **Two-Stage Processing**: Uses GPT-3.5 for initial filtering (keep/discard) and GPT-4 for detailed parsing of articles deemed relevant
- **Joplin Integration**: Sends processed articles directly to Joplin via the Webclipper API (can be enabled/disabled)
- **Tagging System**: Create, manage, and assign custom tags to articles for better organisation
- **Article Age Filtering**: Automatically skip processing of older articles based on configurable maximum age setting
- **Customisable Prompts**: Modify the prompts used for both filtering and parsing stages
- **Persistent Settings**: All configurations are stored in a SQLite database
- **Background Processing**: Automatic scheduled checking of feeds and processing of articles

## Setup

1. Clone this repository
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Configure your environment:
   - OpenAI API Key
   - Joplin Webclipper API URL and token
4. Make sure you top up your OpenAI credit balance AND set a sensible spending limit

## Running the Application

```bash
python start.py
```

This will start the CTI Monitor application with UI (accessible at http://localhost:5000)

## Usage

1. **Configure Settings**: Visit the Settings page to set up your OpenAI API key and Joplin Webclipper details
   - Set the maximum article age (in days) to automatically skip processing older articles (0 = no limit)

![settings](https://github.com/user-attachments/assets/7cadf150-267a-4afc-a3ee-78fdd759f605)

2. **Add RSS Feeds**: Add and manage RSS feeds on the Feeds page
![feeds_view](https://github.com/user-attachments/assets/ab4e9cc1-f1c5-45cb-88c5-bfc02f33ce1b)
3. **Customise Prompts**: Modify the prompts used for filtering and parsing on the Prompts page
   - **IMPORTANT**: When customising the parse prompt (GPT-4), always preserve the JSON structure `{"summary": "...", "threat_groups": [...], "ttp": [...], "tags": [...]}` or the system may fail to parse the response correctly
4. **Manage Tags**: Create and edit tags with custom names and colours for article categorisation
![tags](https://github.com/user-attachments/assets/525fe996-4f18-4423-a7db-e57a8716fe62)
5. **Monitor Articles**: View and manually process articles on the Articles page
   - Filter articles by feed, processing status, date range, and tags
   - Assign tags to articles for better organisation
![processed_article](https://github.com/user-attachments/assets/f0c8ab34-0075-4015-85a2-bae01b76326e)
6. **Running the Scheduler**: Use the dedicated script to run the background scheduler
   ```bash
   python run_scheduler.py
   ```
7. **Process Articles Immediately**: Process pending articles without waiting for the scheduler
   ```bash
   python run_process_articles.py
   ```
   > Note: The older `process_articles.py` script is deprecated and will be removed in a future version. Please use `run_process_articles.py` instead as it properly disables scheduler initialization.
8. **Automatic Processing**: Articles are automatically fetched and processed based on the configured schedule

## API Endpoints

- `POST /process`: Process an article and send it to Joplin
  - Requires JSON with `title` and `content` fields
- `GET /usage`: Check OpenAI API usage
- `GET /api/tags`: Get all available tags
  - Returns JSON with a list of tags including id, name, and color
- `POST /api/articles/<id>/tags`: Update tags for a specific article
  - Requires JSON with `tag_ids` array of tag IDs
  - Returns JSON with success status

## Development

To run the application locally for development:

```bash
pip install -r requirements.txt
python start.py
```

The start script will:
1. Check for required dependencies
2. Initialize the database with sample RSS feeds if empty
3. Start the Flask application
4. Open your browser to the application

## Troubleshooting

### Scheduler Issues

If the scheduler isn't processing articles:

1. **Transaction Errors**: If you see "A transaction is already begun on this Session" errors, restart the scheduler using `python run_scheduler.py`
2. **No Articles Processing**: Make sure there are unprocessed articles in the database and your OpenAI API key is valid
3. **Environment Variables**: The scheduler requires `MAIN_PROCESS=true` environment variable, which is set automatically in the `run_scheduler.py` script
4. **Lock Files**: Check for stale lock files in the project directory if processing seems stuck

### Article Age Filtering

1. **Setting Value**: A value of 0 means no age limit (all articles will be processed)
2. **Missing Publication Date**: Articles without a publication date will not be filtered by age
3. **Already Processed**: Articles already marked as processed will not be reprocessed even if they match the age criteria

### OpenAI API Issues

1. **Rate Limits**: If you encounter rate limit errors, the system will pause and retry automatically
2. **Invalid API Key**: Check your API key in the settings page if articles aren't being processed
3. **Model Availability**: Ensure you have access to the models specified in your prompts (GPT-3.5 and GPT-4)

## License

This project is open source and available under the MIT License.
