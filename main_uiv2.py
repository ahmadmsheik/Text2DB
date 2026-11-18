import streamlit as st
from auth_utils import register_user, login_user
from llm_utils import classify_input, generate_sql_query, generate_general_response, generate_correction_responsev2
from db_utils import (create_db_reader,
                      run_query,
                      save_db_list_with_connection,
                      try_connect_to_database,
                      load_database_connections)
from self_correction_loop import log_correction
from memory_utils import get_memory, update_memory, save_memory_to_disk
import pandas as pd
from rag_training import index_sql_qa_pair, add_sql_qa_batch
import matplotlib.pyplot as plt
import seaborn as sns
import json
from save_schema_descriptions import load_schema_for_db
from v2 import extract_create_table_list, generate_table_descriptions, split_described_chunks_per_table, extract_join_graph_from_db, save_join_graph
from rag_systemv2 import index_schema_chunks_rag
from llm_utilsv2 import run_text_to_sql_pipeline


st.set_page_config(page_title="AI SQL Assistant", layout="wide")

# Session state init
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False  
    st.session_state.user_id = None
    st.session_state.role = None
    st.session_state.chat_history = []

st.title("🧠 AI SQL + RAG Assistant")

if not st.session_state.authenticated:
    st.subheader("🔐 Login / Register")
    auth_choice = st.radio("Choose an action:", ["Login", "Register"])
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")

    if auth_choice == "Register":
        role = st.selectbox("Role", ["user", "admin"])

    if st.button("Submit"):
        if auth_choice == "Login":
            result = login_user(username, password)
        else:
            result = register_user(username, password, role)

        if result["success"]:
            st.session_state.authenticated = True
            st.session_state.user_id = result["user_id"]
            st.session_state.role = result.get("role")
            st.success("Login successful!")
            st.rerun()
        else:
            st.error(result["message"])


elif st.session_state.authenticated:
    
    with st.sidebar:
        st.markdown("## ⚙️ Settings")

        if st.session_state.authenticated:
            st.markdown(f"👤 Logged in as: **{st.session_state.role}**")
            if st.button("🚪 Logout"):
                save_memory_to_disk(st.session_state.user_id)
                st.session_state.clear()
                st.rerun()
                
            saved_connections = load_database_connections()

            if saved_connections:
                db_names = list(saved_connections.keys())
                selected_db = st.selectbox("🗂️ Select a database", db_names)

                if selected_db:
                    st.session_state["db_uri"] = saved_connections[selected_db]
                    st.session_state["connected_db_name"] = selected_db
                    st.success(f"📡 Connected to {selected_db}")

            else:
                st.info("ℹ️ No saved databases found. Go to the 'Connect to SQL Server' tab to add one.")
    
    tabs = st.tabs(["💬 Chat", "📊 Charts", "🛍️ Connect to SQL Server", "➕ Add Question & Query"])

    with tabs[0]:
        if "db_uri" not in st.session_state:
            st.warning("⚠️ Please connect to a SQL Server and select a database in the 'Connect to SQL Server' tab.")
        else:    

            db = create_db_reader(st.session_state["db_uri"])

            st.subheader("💬 Ask a question")
            question = st.text_input("Your Question")

            if st.button("Ask") and question:
                update_memory(st.session_state.user_id, "user", question)
                route = classify_input(question)
                

                if route == "sql":
                    db_name = st.session_state.get("connected_db_name")
                    sql_query, table_descriptions, joins = run_text_to_sql_pipeline(question, db_name)

                    db_name = st.session_state.get("connected_db_name")
                    success, result = run_query(sql_query, db_name)
                    if success:
                        if isinstance(result, list) and all(isinstance(row, dict) for row in result):
                            df = pd.DataFrame(result)
                            st.dataframe(df)
                            answer = df.to_markdown(index=False) 
                        else:
                            answer = str(result)
                        
                    else:
                        st.error("❌ Query failed.")
                        st.code(sql_query, language="sql")
                        st.error(f"Error: {result}")
                        corrected_query = corrected_query = generate_correction_responsev2(
                                                            question=question,
                                                            bad_query=sql_query,
                                                            error_message=result,
                                                            table_descriptions=table_descriptions,
                                                            joins=joins
                                                        )

                        success, result = run_query(corrected_query, db_name)
                        
                        if success:
                            st.success("✅ Auto-correction successful!")
                            st.code(corrected_query, language="sql")

                            if isinstance(result, list) and all(isinstance(row, dict) for row in result):
                                df = pd.DataFrame(result)
                                st.dataframe(df)
                                answer = df.to_markdown(index=False)
                            else:
                                answer = str(result)
                            
                            # log_correction(
                            #     prompt=question,
                            #     schema=schema,
                            #     corrected_query=corrected_query,
                            #     bad_query=sql_query,
                            #     error_message=result
                            # )
                        else:
                            st.error("❌ Correction also failed.")
                            st.code(corrected_query, language="sql")
                            st.error(f"Second error: {result}")
                            answer = "Both original and corrected queries failed. Please try rephrasing your question."
                            
                        
                else:
                    answer = generate_general_response(question, get_memory(st.session_state.user_id))

                st.session_state.chat_history.append((question, str(answer)))
                update_memory(st.session_state.user_id, "assistant", str(answer))

            for q, a in reversed(st.session_state.chat_history):
                st.markdown(f"**🧑 You:** {q}")
                st.markdown(f"**🤖 Assistant:** {a}")
            
    with tabs[1]:
        st.subheader("📊 Visualize Data from Natural Language")

        if "db_uri" not in st.session_state:
            st.warning("⚠️ Please connect to a SQL Server and select a database in the 'Connect to SQL Server' tab.")
        
        else:

            db = create_db_reader(st.session_state["db_uri"])

            user_question = st.text_input("📝 Ask a question to visualize", key="chart_question")
            chart_type = st.selectbox("📈 Choose chart type", ["Bar Chart", "Line Chart", "Scatter Plot"], key="chart_type")

            if st.button("🎨 Generate Chart from Question"):
                if not user_question.strip():
                    st.warning("⚠️ Please enter a question.")
                else:
                    sql_query, schema = generate_sql_query(user_question)
                    st.session_state.chart_sql = sql_query 
                    st.code(sql_query, language="sql")

                    db_name = st.session_state.get("connected_db_name")
                    success, result = run_query(sql_query, db_name)
                    if isinstance(result, list) and all(isinstance(row, dict) for row in result):
                        df = pd.DataFrame(result)
                        for col in df.columns:
                            df[col] = pd.to_numeric(df[col], errors='ignore')
                        st.session_state.chart_df = df  
                    else:
                        st.session_state.chart_df = None
                        st.error("❌ Query didn't return valid data.")

            if "chart_df" in st.session_state and st.session_state.chart_df is not None:
                df = st.session_state.chart_df
                st.dataframe(df)

                numeric_cols = df.select_dtypes(include="number").columns.tolist()
                if len(numeric_cols) >= 1:
                    x_axis = st.selectbox("🧭 X-axis", df.columns, index=0, key="x_axis")
                    y_axis = st.selectbox("📐 Y-axis", numeric_cols, index=0, key="y_axis")

                    fig, ax = plt.subplots()
                    if chart_type == "Bar Chart":
                        sns.barplot(x=df[x_axis], y=df[y_axis], ax=ax)
                    elif chart_type == "Line Chart":
                        sns.lineplot(x=df[x_axis], y=df[y_axis], ax=ax)
                    elif chart_type == "Scatter Plot":
                        sns.scatterplot(x=df[x_axis], y=df[y_axis], ax=ax)

                    st.pyplot(fig)
                else:
                    st.warning("⚠️ Not enough numeric columns to plot.")



    with tabs[2]:
        st.markdown("## 🛠 Connect to SQL Server + Schema Description Embedding")

        if "last_schema" not in st.session_state:
            server = st.text_input("🔌 Server", value=st.session_state.get("server", "localhost"))
            driver = st.text_input("🚗 ODBC Driver", value=st.session_state.get("driver", "ODBC Driver 17 for SQL Server"))
            db_name = st.text_input("🗄️ Target Database Name (must already exist)")
            st.session_state["db_name_added"] = db_name

            if st.button("🔗 Connect and Describe Schema"):
                success, result = try_connect_to_database(server, db_name)
                if success:
                    connection_uri = result
                    save_db_list_with_connection(db_name, connection_uri)

                    st.session_state["server"] = server
                    st.session_state["driver"] = driver
                    st.session_state["db_uri"] = connection_uri
                    st.session_state["available_dbs"] = [db_name]
                    st.session_state["db_name_added"] = db_name

                    try:
                        schema_chunks = extract_create_table_list(connection_uri)
                        described_chunks = generate_table_descriptions(schema_chunks)
                        print("Described Chunks: ", described_chunks)
                        st.session_state["last_schema"] = described_chunks
                        
                        chunks = split_described_chunks_per_table(described_chunks)
                        
                        st.session_state["last_schema"] = chunks
                        
                        index_schema_chunks_rag(chunks, db_name)
                        
                        join_graph = extract_join_graph_from_db(connection_uri)
                        print(join_graph)
                        
                        save_join_graph(db_name=db_name,
                                        join_graph=join_graph)
                        
                        st.success("✅ Schema described and indexed.")
                        st.rerun()
                    except Exception as e:
                        st.warning(f"⚠️ Failed to extract or index schema: {e}")
                else:
                    st.error(f"❌ {result}")

        else:
            st.markdown("### 🧾 Indexed Schema Preview")

            if isinstance(st.session_state["last_schema"], list):
                for chunk in st.session_state["last_schema"]:
                    st.code(chunk, language="sql")

            if st.button("✅ Finalize & Clear Session"):
                for key in ["last_schema", "db_uri", "db_name_added"]:
                    st.session_state.pop(key, None)
                st.success("✅ Session cleared.")
                st.rerun()


   
    with tabs[3]:
        if st.session_state.role == "admin":
            st.subheader("➕ Add a Question and Corresponding SQL Query")

            question_input = st.text_area("📝 Question", height=100)
            query_input = st.text_area("🧾 SQL Query", height=150)
            
            if st.button("Save to SQL QA DB"):
                if not question_input.strip() or not query_input.strip():
                    st.warning("⚠️ Both question and query are required.")
                else:
                    index_sql_qa_pair(question_input, query_input)
                    st.success("✅ Saved to SQL QA vector DB.")
            
            
            st.markdown("---")
            uploaded_file = st.file_uploader("📂 Upload JSON File (with question-query pairs)", type="json")

            if uploaded_file is not None:
                try:
                    import json
                    content = json.load(uploaded_file)
                    count = add_sql_qa_batch(content)
                    st.success(f"✅ Uploaded and indexed {count} Q&A pairs.")
                except Exception as e:
                    st.error(f"❌ Failed to process file: {e}")
            
        else:
            st.warning("⛔ Only admins can access this tab.")