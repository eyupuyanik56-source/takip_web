import os
import sys
import re
import sqlite3
import subprocess
from datetime import date, datetime
from pathlib import Path

import pandas as pd


# ============================================================
# AKADEMİK İŞ TAKİP VE KANIT DOSYASI SİSTEMİ
# ============================================================
# Kurulum:
# pip install streamlit pandas streamlit-autorefresh
#
# Çalıştırma:
# streamlit run des.py --server.address 0.0.0.0 --server.port 8501
#
# Aynı ağdaki ikinci kullanıcı:
# http://BILGISAYARIN_IPV4_ADRESI:8501
# ============================================================


def ensure_streamlit_run():
    """
    Dosya yanlışlıkla 'python des.py' şeklinde çalıştırılırsa,
    uygulamayı otomatik olarak Streamlit ile başlatır.
    """

    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx

        if get_script_run_ctx() is None:
            print("\nBu program bir Streamlit uygulamasıdır.")
            print("Tarayıcıda açılması için Streamlit ile başlatılıyor...\n")

            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "streamlit",
                    "run",
                    os.path.abspath(__file__),
                    "--server.address",
                    "0.0.0.0",
                    "--server.port",
                    "8501",
                ]
            )

            sys.exit()

    except ModuleNotFoundError:
        print("\nStreamlit yüklü değil.")
        print("Lütfen önce şu komutu çalıştırın:\n")
        print("pip install streamlit pandas streamlit-autorefresh\n")
        sys.exit()


ensure_streamlit_run()

import streamlit as st

try:
    from streamlit_autorefresh import st_autorefresh
except ModuleNotFoundError:
    st_autorefresh = None


BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "akademik_is_takip.db"
EVIDENCE_DIR = BASE_DIR / "kanit_dosyalari"


DEFAULT_TASKS = [
    "Literatür yazma",
    "Veri toplama",
    "Etik kurul onayı",
    "Anket hazırlama",
    "Yöntem",
    "Analizler",
]


STATUS_OPTIONS = [
    "Yapılmadı",
    "Devam ediyor",
    "Tamamlandı",
]


def get_connection():
    """
    SQLite bağlantısı.
    WAL modu iki kişinin aynı anda kullanımı için daha sağlıklı çalışır.
    """

    conn = sqlite3.connect(
        DB_PATH,
        timeout=30,
        check_same_thread=False,
    )

    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    conn.execute("PRAGMA foreign_keys=ON;")

    return conn


def clean_filename(filename):
    """
    Yüklenen dosya adını güvenli ve benzersiz hale getirir.
    """

    name = Path(filename).stem
    suffix = Path(filename).suffix

    name = re.sub(r"[^a-zA-Z0-9ığüşöçİĞÜŞÖÇ_-]", "_", name)
    name = re.sub(r"_+", "_", name)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")

    return f"{name}_{timestamp}{suffix}"


def initialize_database():
    EVIDENCE_DIR.mkdir(exist_ok=True)

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL UNIQUE,
            description TEXT,
            created_at TEXT NOT NULL
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            task_name TEXT NOT NULL,
            responsible_people TEXT,
            status TEXT NOT NULL,
            start_date TEXT,
            due_date TEXT,
            notes TEXT,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(project_id) REFERENCES projects(id)
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS evidence_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER NOT NULL,
            original_filename TEXT NOT NULL,
            saved_filename TEXT NOT NULL,
            file_path TEXT NOT NULL,
            evidence_note TEXT,
            uploaded_at TEXT NOT NULL,
            FOREIGN KEY(task_id) REFERENCES tasks(id)
        )
        """
    )

    conn.commit()
    conn.close()


def create_project(title, description):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO projects (
            title,
            description,
            created_at
        )
        VALUES (?, ?, ?)
        """,
        (
            title,
            description,
            str(date.today()),
        ),
    )

    project_id = cursor.lastrowid

    for task_name in DEFAULT_TASKS:
        cursor.execute(
            """
            INSERT INTO tasks (
                project_id,
                task_name,
                responsible_people,
                status,
                start_date,
                due_date,
                notes,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                project_id,
                task_name,
                "",
                "Yapılmadı",
                "",
                "",
                "",
                str(date.today()),
            ),
        )

    conn.commit()
    conn.close()


def get_projects():
    conn = get_connection()

    df = pd.read_sql_query(
        """
        SELECT
            id,
            title,
            description,
            created_at
        FROM projects
        ORDER BY id DESC
        """,
        conn,
    )

    conn.close()
    return df


def get_tasks(project_id):
    conn = get_connection()

    df = pd.read_sql_query(
        """
        SELECT
            id,
            task_name AS 'İş Kalemi',
            responsible_people AS 'Sorumlu Kişiler',
            status AS 'Durum',
            start_date AS 'Başlama Tarihi',
            due_date AS 'Hedef Tarih',
            notes AS 'Notlar',
            updated_at AS 'Son Güncelleme'
        FROM tasks
        WHERE project_id = ?
        ORDER BY id
        """,
        conn,
        params=(project_id,),
    )

    conn.close()
    return df


def get_tasks_with_evidence_summary(project_id):
    """
    Genel Durum Tablosunda kanıt sayısı ve kanıt dosyaları görünsün diye
    iş kalemleriyle kanıt dosyalarını birleştirir.
    """

    conn = get_connection()

    df = pd.read_sql_query(
        """
        SELECT
            t.id,
            t.task_name AS 'İş Kalemi',
            t.responsible_people AS 'Sorumlu Kişiler',
            t.status AS 'Durum',
            t.start_date AS 'Başlama Tarihi',
            t.due_date AS 'Hedef Tarih',
            t.notes AS 'Notlar',
            t.updated_at AS 'Son Güncelleme',
            COUNT(e.id) AS 'Kanıt Sayısı',
            COALESCE(GROUP_CONCAT(e.original_filename, ' | '), '') AS 'Kanıt Dosyaları'
        FROM tasks t
        LEFT JOIN evidence_files e
            ON t.id = e.task_id
        WHERE t.project_id = ?
        GROUP BY
            t.id,
            t.task_name,
            t.responsible_people,
            t.status,
            t.start_date,
            t.due_date,
            t.notes,
            t.updated_at
        ORDER BY t.id
        """,
        conn,
        params=(project_id,),
    )

    conn.close()
    return df


def update_task(
    task_id,
    responsible_people,
    status,
    start_date,
    due_date,
    notes,
):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        UPDATE tasks
        SET
            responsible_people = ?,
            status = ?,
            start_date = ?,
            due_date = ?,
            notes = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (
            responsible_people,
            status,
            start_date,
            due_date,
            notes,
            str(date.today()),
            task_id,
        ),
    )

    conn.commit()
    conn.close()


def add_custom_task(project_id, task_name):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO tasks (
            project_id,
            task_name,
            responsible_people,
            status,
            start_date,
            due_date,
            notes,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            project_id,
            task_name,
            "",
            "Yapılmadı",
            "",
            "",
            "",
            str(date.today()),
        ),
    )

    conn.commit()
    conn.close()


def save_evidence_file(task_id, uploaded_file, evidence_note):
    saved_filename = clean_filename(uploaded_file.name)
    saved_path = EVIDENCE_DIR / saved_filename

    with open(saved_path, "wb") as file:
        file.write(uploaded_file.getbuffer())

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO evidence_files (
            task_id,
            original_filename,
            saved_filename,
            file_path,
            evidence_note,
            uploaded_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            task_id,
            uploaded_file.name,
            saved_filename,
            str(saved_path),
            evidence_note,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        ),
    )

    conn.commit()
    conn.close()


def get_evidence_files(task_id):
    conn = get_connection()

    df = pd.read_sql_query(
        """
        SELECT
            id,
            original_filename AS 'Dosya Adı',
            saved_filename AS 'Kayıtlı Dosya Adı',
            file_path AS 'Dosya Yolu',
            evidence_note AS 'Kanıt Notu',
            uploaded_at AS 'Yüklenme Tarihi'
        FROM evidence_files
        WHERE task_id = ?
        ORDER BY id DESC
        """,
        conn,
        params=(task_id,),
    )

    conn.close()
    return df


def delete_evidence_file(evidence_id):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT file_path
        FROM evidence_files
        WHERE id = ?
        """,
        (evidence_id,),
    )

    result = cursor.fetchone()

    if result:
        file_path = Path(result[0])

        if file_path.exists():
            try:
                file_path.unlink()
            except PermissionError:
                pass

    cursor.execute(
        """
        DELETE FROM evidence_files
        WHERE id = ?
        """,
        (evidence_id,),
    )

    conn.commit()
    conn.close()


def delete_task(task_id):
    evidence_df = get_evidence_files(task_id)

    for _, row in evidence_df.iterrows():
        delete_evidence_file(int(row["id"]))

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        DELETE FROM tasks
        WHERE id = ?
        """,
        (task_id,),
    )

    conn.commit()
    conn.close()


def delete_project(project_id):
    tasks_df = get_tasks(project_id)

    for _, row in tasks_df.iterrows():
        delete_task(int(row["id"]))

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        DELETE FROM projects
        WHERE id = ?
        """,
        (project_id,),
    )

    conn.commit()
    conn.close()


def calculate_completion(tasks_df):
    if tasks_df.empty:
        return 0

    completed_count = len(
        tasks_df[tasks_df["Durum"] == "Tamamlandı"]
    )

    total_count = len(tasks_df)

    return round(completed_count / total_count, 2)


def calculate_status_counts(tasks_df):
    status_counts = {
        "Yapılmadı": 0,
        "Devam ediyor": 0,
        "Tamamlandı": 0,
    }

    if tasks_df.empty:
        return status_counts

    for status in STATUS_OPTIONS:
        status_counts[status] = len(
            tasks_df[tasks_df["Durum"] == status]
        )

    return status_counts


def show_evidence_files(task_id, key_prefix):
    """
    Kanıt dosyalarını gösterir.

    key_prefix parametresi önemlidir.
    Aynı kanıt dosyası hem genel tabloda hem ayrıntı bölümünde
    gösterildiği için Streamlit buton anahtarları benzersiz olmalıdır.
    """

    evidence_df = get_evidence_files(task_id)

    if evidence_df.empty:
        st.info("Bu iş kalemine ait henüz kanıt dosyası yok.")
        return

    for _, evidence_row in evidence_df.iterrows():
        evidence_id = int(evidence_row["id"])
        file_path = Path(evidence_row["Dosya Yolu"])

        unique_key_base = f"{key_prefix}_{task_id}_{evidence_id}"

        with st.container(border=True):
            st.markdown(f"**Dosya:** {evidence_row['Dosya Adı']}")
            st.write(f"**Yüklenme tarihi:** {evidence_row['Yüklenme Tarihi']}")

            if evidence_row["Kanıt Notu"]:
                st.write(f"**Kanıt notu:** {evidence_row['Kanıt Notu']}")

            if file_path.exists():
                with open(file_path, "rb") as file:
                    file_bytes = file.read()

                st.download_button(
                    label="Dosyayı indir / aç",
                    data=file_bytes,
                    file_name=evidence_row["Dosya Adı"],
                    key=f"download_{unique_key_base}",
                )
            else:
                st.error(
                    "Bu dosya veritabanında kayıtlıdır; ancak klasörde bulunamadı."
                )

            if st.button(
                "Bu kanıt dosyasını sil",
                key=f"delete_{unique_key_base}",
            ):
                delete_evidence_file(evidence_id)
                st.warning("Kanıt dosyası silindi.")
                st.rerun()


def app():
    st.set_page_config(
        page_title="Akademik İş Takip Sistemi",
        page_icon="📚",
        layout="wide",
    )

    initialize_database()

    if st_autorefresh is not None:
        st_autorefresh(
            interval=5000,
            key="academic_tracker_autorefresh",
        )

    st.title("📚 Akademik İş Takip ve Kanıt Dosyası Sistemi")

    st.write(
        "Bu sistem; akademik çalışmaların literatür, veri toplama, "
        "etik kurul, anket hazırlama, yöntem ve analiz aşamalarını "
        "izlemek ve her aşamaya ilişkin kanıt dosyalarını saklamak için "
        "hazırlanmıştır."
    )

    if st_autorefresh is None:
        st.warning(
            "Anlık yenileme için ek paket yüklü değil. "
            "Kurmak için terminalde şu komutu çalıştırınız: "
            "pip install streamlit-autorefresh"
        )

    st.sidebar.title("İşlemler")

    with st.sidebar:
        st.subheader("Yeni Akademik Çalışma")

        new_title = st.text_input(
            "Ana başlık",
            placeholder="Örn. Gastronomi Turizminde Sürdürülebilirlik Algısı",
        )

        new_description = st.text_area(
            "Kısa açıklama / araştırma problemi",
            placeholder="Çalışmanın temel problemi, amacı veya kapsamı...",
        )

        if st.button("Yeni çalışma oluştur"):
            if not new_title.strip():
                st.warning("Ana başlık boş bırakılamaz.")
            else:
                try:
                    create_project(
                        new_title.strip(),
                        new_description.strip(),
                    )

                    st.success("Yeni akademik çalışma oluşturuldu.")
                    st.rerun()

                except sqlite3.IntegrityError:
                    st.error(
                        "Bu ana başlık daha önce kaydedilmiş. "
                        "Lütfen farklı bir başlık giriniz."
                    )

    projects_df = get_projects()

    if projects_df.empty:
        st.info(
            "Henüz kayıtlı bir çalışma bulunmamaktadır. "
            "Sol menüden yeni bir akademik çalışma oluşturabilirsiniz."
        )
        return

    st.markdown("---")

    project_titles = projects_df["title"].tolist()

    selected_title = st.selectbox(
        "Takip etmek istediğiniz akademik çalışmayı seçiniz",
        project_titles,
    )

    selected_project = projects_df[
        projects_df["title"] == selected_title
    ].iloc[0]

    selected_project_id = int(selected_project["id"])

    st.header(selected_project["title"])

    if selected_project["description"]:
        st.info(selected_project["description"])

    tasks_df = get_tasks(selected_project_id)
    summary_df = get_tasks_with_evidence_summary(selected_project_id)

    completion_rate = calculate_completion(tasks_df)
    status_counts = calculate_status_counts(tasks_df)

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Toplam iş kalemi", len(tasks_df))

    with col2:
        st.metric("Tamamlanma oranı", f"%{int(completion_rate * 100)}")

    with col3:
        st.metric("Devam eden iş", status_counts["Devam ediyor"])

    with col4:
        st.metric("Yapılmamış iş", status_counts["Yapılmadı"])

    st.progress(completion_rate)

    st.markdown("### Genel Durum Tablosu")

    display_summary_df = summary_df.drop(columns=["id"])

    st.dataframe(
        display_summary_df,
        use_container_width=True,
        hide_index=True,
    )

    csv_data = display_summary_df.to_csv(index=False).encode("utf-8-sig")

    st.download_button(
        label="Genel durum tablosunu CSV olarak indir",
        data=csv_data,
        file_name=f"{selected_project['title']}_genel_durum_tablosu.csv",
        mime="text/csv",
        key=f"download_summary_csv_{selected_project_id}",
    )

    st.markdown("### Genel Durum Tablosundan Kanıtları Görüntüle")

    if summary_df.empty:
        st.info("Bu çalışmaya ait iş kalemi bulunmamaktadır.")
    else:
        task_options = {}

        for _, row in summary_df.iterrows():
            label = (
                f"{row['İş Kalemi']} "
                f"— Durum: {row['Durum']} "
                f"— Kanıt: {row['Kanıt Sayısı']}"
            )

            task_options[label] = int(row["id"])

        selected_task_label = st.selectbox(
            "Kanıtlarını görmek istediğiniz iş kalemini seçiniz",
            list(task_options.keys()),
            key=f"summary_evidence_selector_{selected_project_id}",
        )

        selected_task_id = task_options[selected_task_label]

        show_evidence_files(
            selected_task_id,
            key_prefix="summary_area",
        )

    st.markdown("---")

    st.markdown("### İş Kalemlerini Güncelle ve Kanıt Dosyası Yükle")

    for _, row in tasks_df.iterrows():
        task_id = int(row["id"])
        evidence_df = get_evidence_files(task_id)
        evidence_count = len(evidence_df)

        expander_title = (
            f"{row['İş Kalemi']} | "
            f"Durum: {row['Durum']} | "
            f"Kanıt dosyası: {evidence_count}"
        )

        with st.expander(expander_title):
            st.markdown("#### İş Bilgileri")

            responsible_people = st.text_input(
                "Kimler tarafından yapılacak / yapıldı?",
                value=row["Sorumlu Kişiler"] if row["Sorumlu Kişiler"] else "",
                key=f"responsible_{task_id}",
            )

            status = st.selectbox(
                "İşin durumu",
                STATUS_OPTIONS,
                index=STATUS_OPTIONS.index(row["Durum"]),
                key=f"status_{task_id}",
            )

            start_date = st.text_input(
                "Başlama tarihi",
                value=row["Başlama Tarihi"] if row["Başlama Tarihi"] else "",
                placeholder="Örn. 2026-04-25",
                key=f"start_date_{task_id}",
            )

            due_date = st.text_input(
                "Hedef tarih",
                value=row["Hedef Tarih"] if row["Hedef Tarih"] else "",
                placeholder="Örn. 2026-05-15",
                key=f"due_date_{task_id}",
            )

            notes = st.text_area(
                "Notlar",
                value=row["Notlar"] if row["Notlar"] else "",
                key=f"notes_{task_id}",
            )

            col_update, col_delete = st.columns(2)

            with col_update:
                if st.button(
                    "Bu iş kalemini güncelle",
                    key=f"update_button_{task_id}",
                ):
                    update_task(
                        task_id=task_id,
                        responsible_people=responsible_people,
                        status=status,
                        start_date=start_date,
                        due_date=due_date,
                        notes=notes,
                    )

                    st.success("İş kalemi güncellendi.")
                    st.rerun()

            with col_delete:
                if st.button(
                    "Bu iş kalemini sil",
                    key=f"delete_task_button_{task_id}",
                ):
                    delete_task(task_id)

                    st.warning("İş kalemi ve ona bağlı kanıt dosyaları silindi.")
                    st.rerun()

            st.markdown("---")
            st.markdown("#### Kanıt Dosyası Yükle")

            evidence_note = st.text_area(
                "Bu kanıt dosyasına ilişkin kısa açıklama",
                placeholder=(
                    "Örn. Etik kurul başvuru formu yüklendi. "
                    "Anketin son hali eklendi. Analiz çıktısı kaydedildi."
                ),
                key=f"evidence_note_{task_id}",
            )

            uploaded_files = st.file_uploader(
                "Dosya seçiniz",
                accept_multiple_files=True,
                key=f"file_uploader_{task_id}",
                help=(
                    "PDF, Word, Excel, görsel, SPSS çıktısı veya başka "
                    "bir kanıt dosyası yükleyebilirsiniz."
                ),
            )

            if st.button(
                "Kanıt dosyalarını kaydet",
                key=f"save_evidence_{task_id}",
            ):
                if not uploaded_files:
                    st.warning("Önce en az bir dosya seçiniz.")
                else:
                    for uploaded_file in uploaded_files:
                        save_evidence_file(
                            task_id=task_id,
                            uploaded_file=uploaded_file,
                            evidence_note=evidence_note.strip(),
                        )

                    st.success("Kanıt dosyaları kaydedildi.")
                    st.rerun()

            st.markdown("---")
            st.markdown("#### Bu İş Kalemine Ait Kayıtlı Kanıt Dosyaları")

            show_evidence_files(
                task_id,
                key_prefix="detail_area",
            )

    st.markdown("---")

    st.markdown("### Yeni İş Kalemi Ekle")

    custom_task_name = st.text_input(
        "Ek iş kalemi",
        placeholder=(
            "Örn. Ölçek uyarlama, pilot uygulama, "
            "hakem düzeltmeleri, makale gönderimi"
        ),
        key=f"custom_task_name_{selected_project_id}",
    )

    if st.button(
        "İş kalemi ekle",
        key=f"add_custom_task_{selected_project_id}",
    ):
        if not custom_task_name.strip():
            st.warning("İş kalemi adı boş bırakılamaz.")
        else:
            add_custom_task(
                selected_project_id,
                custom_task_name.strip(),
            )

            st.success("Yeni iş kalemi eklendi.")
            st.rerun()

    st.markdown("---")

    st.markdown("### Seçili Çalışmayı Sil")

    st.warning(
        "Bu işlem seçili akademik çalışmayı, ona bağlı bütün iş "
        "kalemlerini ve yüklenen kanıt dosyalarını siler."
    )

    confirm_delete = st.checkbox(
        "Bu çalışmayı ve bütün kanıt dosyalarını silmek istediğimi onaylıyorum.",
        key=f"confirm_delete_project_{selected_project_id}",
    )

    if st.button(
        "Seçili çalışmayı sil",
        key=f"delete_project_{selected_project_id}",
    ):
        if confirm_delete:
            delete_project(selected_project_id)

            st.warning("Akademik çalışma ve bağlı kanıt dosyaları silindi.")
            st.rerun()
        else:
            st.error("Silme işlemi için önce onay kutusunu işaretleyiniz.")


if __name__ == "__main__":
    app()