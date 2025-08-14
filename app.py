import streamlit as st
import pandas as pd
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from google.cloud import storage
import tempfile
from datetime import datetime
import json

# ======================
# Leer variables desde st.secrets
# ======================
GMAIL_USER = st.secrets["email"]["GMAIL_USER"]
GMAIL_PASSWORD = st.secrets["email"]["GMAIL_PASSWORD"]
COPY_MAIL = st.secrets["email"]["COPY_MAIL"]
GCS_BUCKET = st.secrets["gcp_config"]["GCS_BUCKET"]
GCP_SERVICE_ACCOUNT = st.secrets["GCP_SERVICE_ACCOUNT"]

# ======================
# Configurar cliente GCP con credenciales temporales
# ======================
with tempfile.NamedTemporaryFile(delete=False, suffix=".json") as temp_file:
    json.dump(GCP_SERVICE_ACCOUNT, temp_file)
    temp_file_path = temp_file.name

storage_client = storage.Client.from_service_account_json(temp_file_path)
bucket = storage_client.bucket(GCS_BUCKET)

# ======================
# Función subir a GCP
# ======================
def upload_to_gcp(df, blob_name):
    try:
        blob = bucket.blob(blob_name)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as temp_csv:
            df.to_csv(temp_csv.name, index=False)
            blob.upload_from_filename(temp_csv.name)
        return f"gs://{GCS_BUCKET}/{blob_name}"
    except Exception as e:
        st.error(f"❌ Error al subir a GCP: {e}")
        return None

# ======================
# Función enviar correo
# ======================
def send_email(df, timestamp):
    try:
        mensaje_html = f"""
        <p>Hola,</p>
        <p>Adjunto encontrarás el detalle de nuevas OTs Facturadas:</p>
        {df.to_html(index=False)}
        <p>Saludos,<br>Bot Retención</p>
        """
        msg = MIMEMultipart()
        msg['From'] = GMAIL_USER
        msg['To'] = GMAIL_USER
        msg['Cc'] = ", ".join(COPY_MAIL)
        msg['Subject'] = f"Archivo procesado - {timestamp}"
        msg.attach(MIMEText(mensaje_html, 'html'))

        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(GMAIL_USER, GMAIL_PASSWORD)
        server.sendmail(GMAIL_USER, [GMAIL_USER] + COPY_MAIL, msg.as_string())
        server.quit()
        st.success("📧 Correo enviado correctamente.")
    except Exception as e:
        st.error(f"❌ Error al enviar el correo: {e}")

# ======================
# Interfaz Streamlit
# ======================
st.title("📤 Carga y Envío de Archivo a GCP + Email")

uploaded_file = st.file_uploader("📂 Subir archivo CSV", type=["csv"])

if "df" not in st.session_state:
    st.session_state.df = None

# Mostrar DataFrame cargado
if uploaded_file:
    st.session_state.df = pd.read_csv(uploaded_file)
    st.write("📊 Vista previa del archivo:")
    st.dataframe(st.session_state.df)

# Botones de acción solo si hay DataFrame cargado
if st.session_state.df is not None:
    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("📤 Subir a GCP y Enviar Correo"):
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            blob_name = f"SurTrading_{timestamp}.csv"

            # Seleccionar columnas a enviar
            cols_select = [
                'Invoice_DATE', 'Repair_Order_Date', 'Odometer',
                'Type_Service', 'VIN', 'Brand', 'Model_Name',
                'Client', 'Phone', 'mail'
            ]
            df_selected = st.session_state.df[cols_select]

            gcs_path = upload_to_gcp(df_selected, blob_name)
            if gcs_path:
                st.success(f"Archivo subido a: {gcs_path}")
                send_email(df_selected, timestamp)

    with col2:
        if st.button("🧹 Limpiar vista"):
            st.session_state.df = None
            st.experimental_rerun()  # Borra la visualización

    with col3:
        fecha_inicio = st.date_input("Fecha inicio")
        fecha_fin = st.date_input("Fecha fin")
        if st.button("📥 Descargar por fechas"):
            df_filtrado = st.session_state.df[
                (pd.to_datetime(st.session_state.df['Invoice_DATE']) >= pd.to_datetime(fecha_inicio)) &
                (pd.to_datetime(st.session_state.df['Invoice_DATE']) <= pd.to_datetime(fecha_fin))
            ]
            if not df_filtrado.empty:
                csv = df_filtrado.to_csv(index=False)
                st.download_button("Descargar CSV", csv, file_name="filtrado.csv", mime="text/csv")
            else:
                st.warning("⚠ No se encontraron registros en el rango seleccionado.")
