import os
import subprocess
import json
import youtube_dl
import logging
from faster_whisper import WhisperModel
import sys
import tiktoken
import requests
import platform


language_dict = {
    "简体中文": [
        "zh",
        "zh-Hans",
        "zh-CN",
        "zh-SG",
        "zh-Hant",
        "zh-HK",
        "zh-MO",
        "zh-TW",
    ],
    "繁體中文": [
        "zh",
        "zh-Hans",
        "zh-CN",
        "zh-SG",
        "zh-Hant",
        "zh-HK",
        "zh-MO",
        "zh-TW",
    ],
    "English": [
        "en",
        "en-AU",
        "en-BZ",
        "en-CA",
        "en-029",
        "en-HK",
        "en-IN",
        "en-IE",
        "en-JM",
        "en-MY",
        "en-NZ",
        "en-PH",
        "en-SG",
        "en-ZA",
        "en-TT",
        "en-AE",
        "en-GB",
        "en-US",
        "en-ZW",
    ],
    "Español": [
        "es",
        "es-AR",
        "es-VE",
        "es-BO",
        "es-CL",
        "es-CO",
        "es-CR",
        "es-CU",
        "es-DO",
        "es-EC",
        "es-SV",
        "es-GT",
        "es-HN",
        "es-419",
        "es-MX",
        "es-NI",
        "es-PA",
        "es-PY",
        "es-PE",
        "es-PR",
        "es-ES",
        "es-US",
        "es-UY",
    ],
    "Français": [
        "fr",
        "fr-BE",
        "fr-CI",
        "fr-CM",
        "fr-CA",
        "fr-029",
        "fr-CD",
        "fr-FR",
        "fr-HT",
        "fr-LU",
        "fr-ML",
        "fr-MA",
        "fr-MC",
        "fr-RE",
        "fr-SN",
        "fr-CH",
    ],
    "Deutsch": ["de", "de-AT", "de-DE", "de-LI", "de-LU", "de-CH"],
    "Português": ["pt", "pt-BR", "pt-PT"],
    "Русский": ["ru", "ru-MD", "ru-RU"],
    "日本語": ["ja", "ja-JP"],
    "العربية": [
        "ar",
        "ar-DZ",
        "ar-BH",
        "ar-EG",
        "ar-IQ",
        "ar-JO",
        "ar-KW",
        "ar-LB",
        "ar-LY",
        "ar-MA",
        "ar-OM",
        "ar-QA",
        "ar-SA",
        "ar-SY",
        "ar-TN",
        "ar-AE",
        "ar-YE",
    ],
    "हिन्दी": ["hi", "hi-IN"],
    "한국어": ["ko", "ko-KR"],
    "Italiano": ["it", "it-IT", "it-CH"],
}


def find_matching_item(a, b):
    set_b = set(b)
    for item in a:
        if item in set_b:
            return item
    return None


def get_video_title(youtube_url):
    ydl_opts = {
        "quiet": True,
        "skip_download": True,
    }

    with youtube_dl.YoutubeDL(ydl_opts) as ydl:
        info_dict = ydl.extract_info(youtube_url, download=False)
        video_title = info_dict.get("title", None)
    return video_title


def download_subtitle(youtube_url, language=["en"], output_path="./", logger=None):
    if logger is None:
        logger = logging.getLogger(__name__)

    ydl_opts = {
        "writesubtitles": True,
        "subtitlesformat": "srt/vtt/ass",
        "skip_download": True,  # Do not download the video
        "outtmpl": output_path + "%(title)s.%(ext)s",
    }

    subtitle_file = None
    with youtube_dl.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(youtube_url, download=False)
    if "subtitles" in info and find_matching_item(language, info["subtitles"]):
        sub_language = find_matching_item(language, info["subtitles"])
        sub_ydl_opts = ydl_opts.copy()
        sub_ydl_opts["subtitleslangs"] = [sub_language]
        logger.info("Subtitle available")
        with youtube_dl.YoutubeDL(sub_ydl_opts) as sub_ydl:
            sub_ydl.download([youtube_url])
        file_list = os.listdir(".")
        for file_name in file_list:
            if ydl.prepare_filename(info)[:-4] in file_name:
                break
        subtitle_file = file_name
    else:
        logger.warning(f"No subtitles available in the selected language.")

    return subtitle_file


def get_file_format(file_path):
    _, file_extension = os.path.splitext(file_path)
    return file_extension


def convert_ass_to_text(ass_file):
    transcription = []
    with open(ass_file, "r", encoding="utf-8") as file:
        for line in file:
            if not line.startswith("Dialogue:"):
                continue
            line = line.split(",", 9)[-1]
            transcription.append(line.strip())

    return " ".join(transcription)


def convert_srt_vtt_to_text(srt_vtt_file):
    transcription = []
    with open(srt_vtt_file, "r", encoding="utf-8") as file:
        for line in file:
            if (
                line.strip()
                and not line.startswith("WEBVTT")
                and "Kind: captions" not in line
                and "Language:" not in line
            ):
                if not line.strip().isdigit() and "-->" not in line:
                    transcription.append(line.strip())

    return " ".join(transcription)


def download_audio(youtube_url, output_path="./", logger=None):
    if logger is None:
        logger = logging.getLogger(__name__)

    filename = None

    def download_hook(d):
        nonlocal filename
        if d["status"] == "finished":
            filename = d["filename"]

    ydl_opts = {
        "format": "bestaudio",
        "outtmpl": output_path + "%(title)s.%(ext)s",
        "progress_hooks": [download_hook],
    }

    with youtube_dl.YoutubeDL(ydl_opts) as ydl:
        ydl.download([youtube_url])

    logger.info(f"Audio downloaded: {filename}")
    return filename


def run_command(command, logger=None):
    if logger is None:
        logger = logging.getLogger(__name__)

    try:
        result = subprocess.run(
            command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        output = result.stdout.decode("utf-8")
        return json.loads(output)
    except subprocess.CalledProcessError as e:
        logger.error("Command failed with error: %s", e.stderr.decode("utf-8"))
        return {"error": e.stderr.decode("utf-8")}
    except json.JSONDecodeError as e:
        logger.error("Failed to parse JSON: %s", str(e))
        return {"error": f"Failed to parse JSON: {str(e)}"}


def whisperAPITranscribe(audio_file, language, api_token, logger=None):
    command = [
        "curl",
        "https://api.openai.com/v1/audio/transcriptions",
        "-H",
        f"Authorization: Bearer {api_token}",
        "-F",
        f"file=@{audio_file}",
        "-F",
        "model=whisper-1",
        "-F",
        f"language={language}",
        "-F",
        "task=transcribe",
    ]
    transcription = run_command(command, logger=logger)["text"]
    return transcription


def fasterWhisperTranscribe(
    file_path, language, model_size="medium.en", update_progress_bar=None, logger=None
):
    if logger is None:
        logger = logging.getLogger(__name__)

    compute_type = "float32" if platform.system() == "Darwin" else "float16"
    model = WhisperModel(model_size, device="auto", compute_type=compute_type)

    if model_size.endswith(".en"):
        segments, info = model.transcribe(file_path, beam_size=5, language="en")
    else:
        segments, info = model.transcribe(file_path, beam_size=5, language=language)

    transcription = ""
    total_duration = round(info.duration, 2)

    for segment in segments:
        transcription += segment.text
        if update_progress_bar is not None:
            update_progress_bar(round(segment.end / total_duration * 0.9, 2))

    with open(file_path + ".txt", "w", encoding="utf-8") as file:
        file.write(transcription)

    os.remove(file_path)

    return transcription


def split_text_by_token_limit_tiktoken(text, token_limit=3000, model="gpt-3.5-turbo"):
    encoding = tiktoken.encoding_for_model(model)
    tokens = encoding.encode(text)
    chunks = []

    for i in range(0, len(tokens), token_limit):
        chunk_tokens = tokens[i : i + token_limit]
        chunk_text = encoding.decode(chunk_tokens)
        chunks.append(chunk_text)

    return chunks


def parse_input(input_string):
    lines = input_string.strip().split("\n")
    blocks = []

    for line in lines:
        line_strip = line.strip()
        if line_strip.startswith("- "):
            blocks.append(
                {
                    "object": "block",
                    "type": "heading_3",
                    "heading_3": {
                        "rich_text": [
                            {"type": "text", "text": {"content": line_strip[2:]}}
                        ]
                    },
                }
            )
        elif line_strip.startswith("* "):
            blocks.append(
                {
                    "object": "block",
                    "type": "bulleted_list_item",
                    "bulleted_list_item": {
                        "rich_text": [
                            {"type": "text", "text": {"content": line_strip[2:]}}
                        ]
                    },
                }
            )

    return blocks


def resource_path(relative_path):
    """Get the absolute path to the resource, works for dev and for PyInstaller"""
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)


def check_property_exists(database_id, property_name, headers):
    url = f"https://api.notion.com/v1/databases/{database_id}"
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        database = response.json()
        return property_name in database["properties"]
    else:
        return False


def add_property_to_database(
    database_id, property_name, property_type, headers, logger=None
):
    if logger is None:
        logger = logging.getLogger(__name__)
    url = f"https://api.notion.com/v1/databases/{database_id}"
    update_payload = {
        "properties": {property_name: {"type": property_type, property_type: {}}}
    }
    response = requests.patch(url, headers=headers, json=update_payload)
    if response.status_code == 200:
        logger.info(f"Property '{property_name}' added to the database.")
    else:
        logger.warning(
            f"Failed to add property to database: {response.status_code}, {response.text}"
        )
