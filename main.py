import os
import json
import re
from pathlib import Path

import streamlit as st
import pandas as pd

from dotenv import load_dotenv
from sqlalchemy import URL, create_engine, inspect

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI

# ===========================
# Load Environment Variables
# ===========================

load_dotenv()

# ===========================
# Streamlit Config
# ===========================

st.set_page_config(
    page_title="Text to SQL",
    page_icon="🗄️",
    layout="wide"
)

DB_DEFAULTS = {
    "db_host": os.getenv("DB_HOST", ""),
    "db_port": os.getenv("DB_PORT", "3306"),
    "db_user": os.getenv("DB_USER", ""),
    "db_password": os.getenv("DB_PASSWORD", ""),
    "db_name": os.getenv("DB_NAME", ""),
}

for key, default in DB_DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = default

st.title("🗄️ Text-to-SQL Assistant")

app_mode = st.radio(
    "Choose a section",
    ["Demo", "Real Database"],
    horizontal=True,
    key="database_mode"
)

# ===========================
# Extract Schema
# ===========================

def create_database_engine(host, port, user, password, database):

    if not host.strip() or not user.strip() or not database.strip():
        raise ValueError("Enter the MySQL host, user, and database name.")

    try:
        port_number = int(port)
    except ValueError as error:
        raise ValueError("MySQL port must be a number between 1 and 65535.") from error

    if not 1 <= port_number <= 65535:
        raise ValueError("MySQL port must be a number between 1 and 65535.")

    database_url = URL.create(
        "mysql+pymysql",
        username=user.strip(),
        password=password,
        host=host.strip(),
        port=port_number,
        database=database.strip(),
    )
    return create_engine(database_url)


def extract_schema(engine, database_name):

    inspector = inspect(engine)

    schema = {
        "database": database_name,
        "tables": []
    }

    for table in inspector.get_table_names():

        table_info = {
            "table_name": table,
            "columns": [],
            "primary_keys": [],
            "foreign_keys": []
        }

        for col in inspector.get_columns(table):

            table_info["columns"].append({

                "name": col["name"],
                "type": str(col["type"]),
                "nullable": col["nullable"]

            })

        pk = inspector.get_pk_constraint(table)

        table_info["primary_keys"] = pk.get(
            "constrained_columns",
            []
        )

        for fk in inspector.get_foreign_keys(table):

            table_info["foreign_keys"].append({

                "column": fk["constrained_columns"],

                "references_table": fk["referred_table"],

                "references_column": fk["referred_columns"]

            })

        schema["tables"].append(table_info)
    return schema


def schema_file_path(database_name):

    safe_database_name = re.sub(
        r"[^A-Za-z0-9_-]+",
        "_",
        database_name.strip(),
    ).strip("_")

    if not safe_database_name:
        raise ValueError("Database name cannot be used to create a schema filename.")

    return Path(__file__).resolve().parent / f"schema_{safe_database_name}.json"


def save_schema(schema, database_name):

    path = schema_file_path(database_name)
    with path.open("w", encoding="utf-8") as schema_file:
        json.dump(schema, schema_file, indent=4)

    return path


def load_schema(database_name):

    path = schema_file_path(database_name)
    if not path.is_file():
        raise FileNotFoundError(
            f"Schema file {path.name} is missing. Save the database settings again."
        )

    with path.open("r", encoding="utf-8") as schema_file:
        return json.load(schema_file)


if app_mode == "Demo":
    demo_database_path = Path(__file__).resolve().parent / "uber.db"
    if not demo_database_path.is_file():
        st.error(f"Demo SQLite database was not found: {demo_database_path.name}")
        st.stop()

    engine = create_engine(URL.create("sqlite", database=str(demo_database_path)))
    schema = extract_schema(engine, demo_database_path.stem)
else:
    engine = None
    schema = None


# ===========================
# Clean SQL
# ===========================

def clean_sql(sql):

    if isinstance(sql, list):
        parts = []

        for block in sql:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and isinstance(block.get("text"), str):
                parts.append(block["text"])
            else:
                raise TypeError(
                    "SQL response content must contain only text blocks."
                )

        sql = "".join(parts)
    elif not isinstance(sql, str):
        raise TypeError(
            "SQL response content must be a string or a list of text blocks."
        )

    sql = re.sub(r"```sql", "", sql, flags=re.IGNORECASE)
    sql = sql.replace("```", "")

    return sql.strip()

# ===========================
# SQL Validation
# ===========================

def validate_sql(sql):

    blocked = [

        "DROP",
        "DELETE",
        "UPDATE",
        "ALTER",
        "INSERT",
        "TRUNCATE",
        "CREATE"

    ]

    upper = sql.upper()

    for keyword in blocked:

        if keyword in upper:

            raise Exception(
                f"{keyword} is not allowed."
            )


def create_llm(provider, api_key, model_name):

    if provider == "Gemini":
        return ChatGoogleGenerativeAI(
            model=model_name,
            google_api_key=api_key,
            temperature=0
        )

    if provider == "Groq":
        return ChatOpenAI(
            model=model_name,
            api_key=api_key,
            base_url="https://api.groq.com/openai/v1",
            temperature=0
        )

    return ChatOpenAI(
        model=model_name,
        api_key=api_key,
        temperature=0
    )


def validate_model_for_provider(provider, model_name):

    model_name = model_name.strip().lower()

    if provider == "Gemini" and not model_name.startswith("gemini-"):
        raise ValueError(
            "Gemini requires a Gemini model name, for example "
            "gemini-2.0-flash."
        )

    if provider == "Groq" and model_name.startswith(("gpt-", "gemini-")):
        raise ValueError(
            "Groq requires a Groq-supported model name, for example "
            "openai/gpt-oss-120b"
        )

    if provider == "OpenAI" and not model_name.startswith(("gpt-", "o1", "o3", "o4")):
        raise ValueError(
            "OpenAI requires an OpenAI model name, for example gpt-4o-mini."
        )


default_models = {
    "OpenAI": "gpt-4o-mini",
    "Gemini": "gemini-3.5-flash",
    "Groq": "openai/gpt-oss-120b"
}

# ===========================
# Sidebar
# ===========================

with st.sidebar:
    st.header("AI Provider")
    provider = st.selectbox(
        "Choose a provider",
        ["OpenAI", "Gemini", "Groq"],
        key="provider"
    )

    model_state_key = f"model_name_{provider.lower()}"
    api_key_state_key = f"api_key_{provider.lower()}"
    if model_state_key not in st.session_state:
        st.session_state[model_state_key] = default_models[provider]
    if api_key_state_key not in st.session_state:
        api_key_name = {
            "OpenAI": "OPENAI_API_KEY",
            "Gemini": "GEMINI_API_KEY",
            "Groq": "GROQ_API_KEY"
        }[provider]
        st.session_state[api_key_state_key] = os.getenv(
            api_key_name,
            os.getenv("GOOGLE_API_KEY", "") if provider == "Gemini" else "",
        )

    st.text_input(
        "Model name",
        key=model_state_key,
        help=f"Default: {default_models[provider]}"
    )
    st.text_input(
        f"{provider} API key",
        type="password",
        key=api_key_state_key,
        help="The key is stored only in this Streamlit session."
    )

    if st.button("Save AI settings for this session"):
        try:
            current_model = st.session_state[model_state_key].strip()
            current_api_key = st.session_state[api_key_state_key].strip()
            if not current_api_key:
                raise ValueError(f"Enter a {provider} API key.")
            if not current_model:
                raise ValueError("Enter a model name.")

            validate_model_for_provider(provider, current_model)
            st.session_state.saved_ai = {
                "provider": provider,
                "model_name": current_model,
                "api_key": current_api_key,
            }
            st.success("AI settings saved for this session.")
        except ValueError as error:
            st.error(f"Could not save AI settings: {error}")

    saved_ai = st.session_state.get("saved_ai")
    if saved_ai:
        st.caption(
            f"Session-saved AI: {saved_ai['provider']} / {saved_ai['model_name']}"
        )
    else:
        st.caption("AI settings have not been saved for this session.")

    st.divider()
    st.header("Database")
    st.caption("Database settings are saved only for this session.")

    if app_mode == "Demo":
        st.subheader("SQLite Demo")
        st.success("Using bundled database: uber.db")

        if st.button("Save demo database for this session"):
            try:
                demo_database_path = Path(__file__).resolve().parent / "uber.db"
                if not demo_database_path.is_file():
                    raise FileNotFoundError(
                        f"Demo SQLite database was not found: {demo_database_path.name}"
                    )

                demo_engine = create_engine(
                    URL.create("sqlite", database=str(demo_database_path))
                )
                demo_schema = extract_schema(demo_engine, demo_database_path.stem)
                schema_path = save_schema(demo_schema, demo_database_path.stem)
                st.session_state.saved_database = {
                    "mode": "Demo",
                    "path": str(demo_database_path),
                    "name": demo_database_path.stem,
                }
                st.success(
                    f"Demo database saved for this session. "
                    f"Schema saved to {schema_path.name}."
                )
            except Exception as error:
                st.error(f"Could not save demo database: {error}")

        if st.checkbox("Show Schema"):
            st.json(schema)
    else:
        st.subheader("MySQL Database")
        st.text_input("Host", key="db_host")
        st.text_input("Port", key="db_port")
        st.text_input("User", key="db_user")
        st.text_input("Password", type="password", key="db_password")
        st.text_input("Database name", key="db_name")

        if st.button("Save database settings for this session"):
            try:
                saved_database = {
                    "host": st.session_state.db_host,
                    "port": st.session_state.db_port,
                    "user": st.session_state.db_user,
                    "password": st.session_state.db_password,
                    "name": st.session_state.db_name.strip(),
                }
                schema_engine = create_database_engine(
                    saved_database["host"],
                    saved_database["port"],
                    saved_database["user"],
                    saved_database["password"],
                    saved_database["name"],
                )
                schema = extract_schema(schema_engine, saved_database["name"])
                schema_path = save_schema(schema, saved_database["name"])
                saved_database["mode"] = "Real Database"
                st.session_state.saved_database = saved_database
                st.success(
                    f"Database settings saved for this session. "
                    f"Schema saved to {schema_path.name}."
                )
            except Exception as error:
                st.error(f"Could not save database settings: {error}")

        if st.checkbox("Show Schema"):
            try:
                schema_engine = create_database_engine(
                    st.session_state.db_host,
                    st.session_state.db_port,
                    st.session_state.db_user,
                    st.session_state.db_password,
                    st.session_state.db_name,
                )
                schema = extract_schema(
                    schema_engine,
                    st.session_state.db_name.strip(),
                )
                st.json(schema)
            except Exception as error:
                st.error(str(error))

    saved_database = st.session_state.get("saved_database")
    if saved_database:
        st.caption(
            f"Session-saved database: {saved_database['name']} "
            f"({saved_database['mode']})"
        )
    else:
        st.caption("Database settings have not been saved for this session.")

# ===========================
# User Question
# ===========================

question = st.text_input(
    "Ask your question",
    placeholder="Show top 10 trips"
)

if st.button("Generate SQL"):

    if question.strip() == "":

        st.warning("Please enter a question.")

        st.stop()

    saved_ai = st.session_state.get("saved_ai")
    if not saved_ai:
        st.error("Save AI settings in the sidebar before generating SQL.")
        st.stop()

    saved_database = st.session_state.get("saved_database")
    if not saved_database or saved_database.get("mode") != app_mode:
        st.error(
            f"Save the {app_mode} database settings in the sidebar before generating SQL."
        )
        st.stop()

    llm = create_llm(
        saved_ai["provider"],
        saved_ai["api_key"],
        saved_ai["model_name"],
    )

    try:
        if app_mode == "Real Database":
            engine = create_database_engine(
                saved_database["host"],
                saved_database["port"],
                saved_database["user"],
                saved_database["password"],
                saved_database["name"],
            )
            schema = load_schema(saved_database["name"])
            sql_dialect = "MySQL"
            dialect_rules = "Return valid MySQL SQL. Use MySQL syntax only."
        else:
            engine = create_engine(
                URL.create("sqlite", database=saved_database["path"])
            )
            schema = load_schema(saved_database["name"])
            sql_dialect = "SQLite"
            dialect_rules = (
                "Return valid SQLite SQL. Use SQLite syntax only. "
                "Use LIMIT instead of TOP."
            )

        schema_text = json.dumps(schema, indent=2)

        prompt = f"""
You are an expert {sql_dialect} developer. Generate read-only queries only.

Database Schema

{schema_text}

Rules

1. Generate ONLY SQL.
2. No explanation.
3. Use only existing tables.
4. Use only existing columns.
5. {dialect_rules}
6. Never wrap SQL inside markdown.
7. Never use ```sql```.
8. Output only SQL.

Question

{question}

SQL
"""

        with st.spinner("Generating SQL..."):

            response = llm.invoke(prompt)

            sql = clean_sql(response.content)

        validate_sql(sql)

        st.subheader("Generated SQL")

        st.code(sql, language="sql")

        with st.spinner("Executing Query..."):
            df = pd.read_sql(sql, engine)

        st.subheader("Query Result")

        st.dataframe(df, use_container_width=True)

        explanation_prompt = f"""
You are a helpful assistant.

Database Schema

{schema_text}

User Question

{question}

SQL Result

{df.to_markdown(index=False)}

Explain the answer in simple English at 5 lines.
"""

        answer = llm.invoke(explanation_prompt)

        st.subheader("Answer")

        st.write(answer.content)

    except Exception as error:
        st.error(str(error))