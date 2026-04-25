import re
import uuid
from datetime import datetime, date
from pathlib import Path

import pandas as pd
import streamlit as st
from supabase import create_client

try:
    from streamlit_autorefresh import st_autorefresh
except ModuleNotFoundError:
    st_autorefresh = None


# ============================================================
# AKADEMİK İŞ TAKİP VE KANIT DOSYASI SİSTEMİ - WEB SÜRÜMÜ
# ============================================================
# Bu sürüm:
# - Verileri Supabase veritabanında saklar.
# - Kanıt dosyalarını Supabase Storage içinde saklar.
# - Streamlit Cloud üzerinden web sayfası gibi çalışır.
# - Durumları renkli etiketlerle gösterir.
# ============================================================


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


BUCKET_NAME = "evidence-files"


# ============================================================
# SUPABASE BAĞLANTISI
# ============================================================

@st.cache_resource
def get_supabase_client():
    supabase_url = st.secrets["SUPABASE_URL"]
    supabase_key = st.secrets["SUPABASE_SERVICE_ROLE_KEY"]

    return create_client(
        supabase_url,
        supabase_key,
    )


supabase = get_supabase_client()


# ============================================================
# YARDIMCI FONKSİYONLAR
# ============================================================

def now_text():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def today_text():
    return str(date.today())


def clean_filename(filename):
    name = Path(filename).stem
    suffix = Path(filename).suffix

    name = re.sub(
        r"[^a-zA-Z0-9ığüşöçİĞÜŞÖÇ_-]",
        "_",
        name,
    )

    name = re.sub(
        r"_+",
        "_",
        name,
    )

    unique_id = uuid.uuid4().hex[:12]

    return f"{name}_{unique_id}{suffix}"


def run_query(response):
    if hasattr(response, "data"):
        return response.data

    return []


def safe_text(value):
    if value is None:
        return ""

    return str(value)


def status_badge(status):
    """
    İş durumunu renkli ve okunabilir etiket olarak döndürür.
    """

    if status == "Tamamlandı":
        return "🟢 Tamamlandı"

    if status == "Devam ediyor":
        return "🟡 Devam ediyor"

    if status == "Yapılmadı":
        return "🔴 Yapılmadı"

    return safe_text(status)


def status_color_for_dataframe(value):
    """
    Pandas Styler için durum hücrelerini renklendirir.
    """

    if value == "🟢 Tamamlandı":
        return "background-color: #d4edda; color: #155724; font-weight: bold;"

    if value == "🟡 Devam ediyor":
        return "background-color: #fff3cd; color: #856404; font-weight: bold;"

    if value == "🔴 Yapılmadı":
        return "background-color: #f8d7da; color: #721c24; font-weight: bold;"

    return ""


# ============================================================
# PROJE İŞLEMLERİ
# ============================================================

def create_project(title, description):
    project_response = (
        supabase
        .table("projects")
        .insert(
            {
                "title": title,
                "description": description,
                "created_at": now_text(),
            }
        )
        .execute()
    )

    project_data = run_query(project_response)

    if not project_data:
        raise Exception("Proje oluşturulamadı.")

    project_id = project_data[0]["id"]

    task_rows = []

    for task_name in DEFAULT_TASKS:
        task_rows.append(
            {
                "project_id": project_id,
                "task_name": task_name,
                "responsible_people": "",
                "status": "Yapılmadı",
                "start_date": "",
                "due_date": "",
                "notes": "",
                "updated_at": now_text(),
            }
        )

    (
        supabase
        .table("tasks")
        .insert(task_rows)
        .execute()
    )

    return project_id


def get_projects():
    response = (
        supabase
        .table("projects")
        .select("*")
        .order("id", desc=True)
        .execute()
    )

    data = run_query(response)

    if not data:
        return pd.DataFrame(
            columns=[
                "id",
                "title",
                "description",
                "created_at",
            ]
        )

    return pd.DataFrame(data)


def delete_project(project_id):
    tasks_df = get_tasks(project_id)

    for _, task_row in tasks_df.iterrows():
        delete_task(int(task_row["id"]))

    (
        supabase
        .table("projects")
        .delete()
        .eq("id", project_id)
        .execute()
    )


# ============================================================
# İŞ KALEMİ İŞLEMLERİ
# ============================================================

def get_tasks(project_id):
    response = (
        supabase
        .table("tasks")
        .select("*")
        .eq("project_id", project_id)
        .order("id")
        .execute()
    )

    data = run_query(response)

    if not data:
        return pd.DataFrame(
            columns=[
                "id",
                "project_id",
                "task_name",
                "responsible_people",
                "status",
                "start_date",
                "due_date",
                "notes",
                "updated_at",
            ]
        )

    return pd.DataFrame(data)


def get_tasks_display(project_id):
    tasks_df = get_tasks(project_id)

    if tasks_df.empty:
        return pd.DataFrame(
            columns=[
                "id",
                "İş Kalemi",
                "Sorumlu Kişiler",
                "Durum",
                "Başlama Tarihi",
                "Hedef Tarih",
                "Notlar",
                "Son Güncelleme",
            ]
        )

    display_df = tasks_df.rename(
        columns={
            "task_name": "İş Kalemi",
            "responsible_people": "Sorumlu Kişiler",
            "status": "Durum",
            "start_date": "Başlama Tarihi",
            "due_date": "Hedef Tarih",
            "notes": "Notlar",
            "updated_at": "Son Güncelleme",
        }
    )

    return display_df[
        [
            "id",
            "İş Kalemi",
            "Sorumlu Kişiler",
            "Durum",
            "Başlama Tarihi",
            "Hedef Tarih",
            "Notlar",
            "Son Güncelleme",
        ]
    ]


def add_custom_task(project_id, task_name):
    (
        supabase
        .table("tasks")
        .insert(
            {
                "project_id": project_id,
                "task_name": task_name,
                "responsible_people": "",
                "status": "Yapılmadı",
                "start_date": "",
                "due_date": "",
                "notes": "",
                "updated_at": now_text(),
            }
        )
        .execute()
    )


def update_task(
    task_id,
    responsible_people,
    status,
    start_date,
    due_date,
    notes,
):
    (
        supabase
        .table("tasks")
        .update(
            {
                "responsible_people": responsible_people,
                "status": status,
                "start_date": start_date,
                "due_date": due_date,
                "notes": notes,
                "updated_at": now_text(),
            }
        )
        .eq("id", task_id)
        .execute()
    )


def delete_task(task_id):
    evidence_df = get_evidence_files(task_id)

    for _, evidence_row in evidence_df.iterrows():
        delete_evidence_file(
            evidence_id=int(evidence_row["id"]),
            storage_path=evidence_row["storage_path"],
        )

    (
        supabase
        .table("tasks")
        .delete()
        .eq("id", task_id)
        .execute()
    )


# ============================================================
# KANIT DOSYASI İŞLEMLERİ
# ============================================================

def save_evidence_file(
    project_id,
    task_id,
    uploaded_file,
    evidence_note,
):
    cleaned_name = clean_filename(uploaded_file.name)

    storage_path = (
        f"project_{project_id}/"
        f"task_{task_id}/"
        f"{cleaned_name}"
    )

    file_bytes = uploaded_file.getvalue()

    (
        supabase
        .storage
        .from_(BUCKET_NAME)
        .upload(
            path=storage_path,
            file=file_bytes,
            file_options={
                "content-type": uploaded_file.type or "application/octet-stream",
                "upsert": "false",
            },
        )
    )

    (
        supabase
        .table("evidence_files")
        .insert(
            {
                "task_id": task_id,
                "original_filename": uploaded_file.name,
                "storage_path": storage_path,
                "evidence_note": evidence_note,
                "uploaded_at": now_text(),
            }
        )
        .execute()
    )


def get_evidence_files(task_id):
    response = (
        supabase
        .table("evidence_files")
        .select("*")
        .eq("task_id", task_id)
        .order("id", desc=True)
        .execute()
    )

    data = run_query(response)

    if not data:
        return pd.DataFrame(
            columns=[
                "id",
                "task_id",
                "original_filename",
                "storage_path",
                "evidence_note",
                "uploaded_at",
            ]
        )

    return pd.DataFrame(data)


def get_evidence_count(task_id):
    evidence_df = get_evidence_files(task_id)
    return len(evidence_df)


def get_evidence_names(task_id):
    evidence_df = get_evidence_files(task_id)

    if evidence_df.empty:
        return ""

    names = evidence_df["original_filename"].tolist()

    return " | ".join(names)


def download_evidence_file(storage_path):
    result = (
        supabase
        .storage
        .from_(BUCKET_NAME)
        .download(storage_path)
    )

    return result


def delete_evidence_file(evidence_id, storage_path):
    try:
        (
            supabase
            .storage
            .from_(BUCKET_NAME)
            .remove([storage_path])
        )
    except Exception:
        pass

    (
        supabase
        .table("evidence_files")
        .delete()
        .eq("id", evidence_id)
        .execute()
    )


# ============================================================
# GENEL TABLO VE İSTATİSTİKLER
# ============================================================

def get_summary_table(project_id):
    tasks_df = get_tasks_display(project_id)

    if tasks_df.empty:
        return tasks_df

    evidence_counts = []
    evidence_names = []

    for _, row in tasks_df.iterrows():
        task_id = int(row["id"])

        evidence_counts.append(
            get_evidence_count(task_id)
        )

        evidence_names.append(
            get_evidence_names(task_id)
        )

    tasks_df["Kanıt Sayısı"] = evidence_counts
    tasks_df["Kanıt Dosyaları"] = evidence_names

    return tasks_df


def calculate_completion(tasks_df):
    if tasks_df.empty:
        return 0

    completed_count = len(
        tasks_df[tasks_df["status"] == "Tamamlandı"]
    )

    total_count = len(tasks_df)

    if total_count == 0:
        return 0

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
            tasks_df[tasks_df["status"] == status]
        )

    return status_counts


# ============================================================
# KANIT DOSYALARINI EKRANDA GÖSTERME
# ============================================================

def show_evidence_files(task_id, key_prefix):
    evidence_df = get_evidence_files(task_id)

    if evidence_df.empty:
        st.info("Bu iş kalemine ait henüz kanıt dosyası bulunmuyor.")
        return

    for _, evidence_row in evidence_df.iterrows():
        evidence_id = int(evidence_row["id"])
        storage_path = evidence_row["storage_path"]
        original_filename = evidence_row["original_filename"]
        evidence_note = safe_text(evidence_row["evidence_note"])
        uploaded_at = safe_text(evidence_row["uploaded_at"])

        unique_key = f"{key_prefix}_{task_id}_{evidence_id}"

        with st.container(border=True):
            st.markdown(f"**Dosya:** {original_filename}")
            st.write(f"**Yüklenme tarihi:** {uploaded_at}")

            if evidence_note:
                st.write(f"**Kanıt notu:** {evidence_note}")

            try:
                file_bytes = download_evidence_file(storage_path)

                st.download_button(
                    label="Dosyayı indir / aç",
                    data=file_bytes,
                    file_name=original_filename,
                    key=f"download_{unique_key}",
                )

            except Exception:
                st.error(
                    "Dosya kaydı var; ancak depolama alanından indirilemedi."
                )

            if st.button(
                "Bu kanıt dosyasını sil",
                key=f"delete_{unique_key}",
            ):
                delete_evidence_file(
                    evidence_id=evidence_id,
                    storage_path=storage_path,
                )

                st.warning("Kanıt dosyası silindi.")
                st.rerun()


# ============================================================
# STREAMLIT ARAYÜZÜ
# ============================================================

def app():
    st.set_page_config(
        page_title="Akademik İş Takip Sistemi",
        page_icon="📚",
        layout="wide",
    )

    if st_autorefresh is not None:
        st_autorefresh(
            interval=5000,
            key="academic_tracker_autorefresh",
        )

    st.title("📚 Akademik İş Takip ve Kanıt Dosyası Sistemi")

    st.write(
        "Bu sistem; akademik çalışmaların literatür, veri toplama, "
        "etik kurul, anket hazırlama, yöntem ve analiz süreçlerini "
        "izlemek ve her aşamaya ilişkin kanıt dosyalarını saklamak için "
        "hazırlanmıştır."
    )

    st.markdown(
        """
        **Durum göstergeleri:**  
        🔴 Yapılmadı &nbsp;&nbsp; 🟡 Devam ediyor &nbsp;&nbsp; 🟢 Tamamlandı
        """
    )

    if st_autorefresh is None:
        st.warning(
            "Otomatik yenileme paketi kurulu değil. "
            "requirements.txt dosyasına streamlit-autorefresh eklenmelidir."
        )

    with st.sidebar:
        st.title("İşlemler")

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
                        title=new_title.strip(),
                        description=new_description.strip(),
                    )

                    st.success("Yeni akademik çalışma oluşturuldu.")
                    st.rerun()

                except Exception as error:
                    st.error(
                        "Çalışma oluşturulamadı. "
                        "Aynı başlık daha önce kullanılmış olabilir."
                    )
                    st.caption(str(error))

    projects_df = get_projects()

    if projects_df.empty:
        st.info(
            "Henüz kayıtlı bir akademik çalışma bulunmamaktadır. "
            "Sol menüden yeni bir çalışma oluşturabilirsiniz."
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

    if safe_text(selected_project.get("description", "")):
        st.info(selected_project["description"])

    raw_tasks_df = get_tasks(selected_project_id)
    summary_df = get_summary_table(selected_project_id)

    completion_rate = calculate_completion(raw_tasks_df)
    status_counts = calculate_status_counts(raw_tasks_df)

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            "Toplam iş kalemi",
            len(raw_tasks_df),
        )

    with col2:
        st.metric(
            "Tamamlanma oranı",
            f"%{int(completion_rate * 100)}",
        )

    with col3:
        st.metric(
            "Devam eden iş",
            status_counts["Devam ediyor"],
        )

    with col4:
        st.metric(
            "Yapılmamış iş",
            status_counts["Yapılmadı"],
        )

    st.progress(completion_rate)

    st.markdown("### Genel Durum Tablosu")

    if summary_df.empty:
        st.info("Bu çalışmaya ait henüz iş kalemi bulunmamaktadır.")
    else:
        display_summary_df = summary_df.drop(
            columns=["id"],
            errors="ignore",
        )

        if "Durum" in display_summary_df.columns:
            display_summary_df["Durum"] = display_summary_df["Durum"].apply(
                status_badge
            )

        styled_summary_df = display_summary_df.style.map(
            status_color_for_dataframe,
            subset=["Durum"],
        )

        st.dataframe(
            styled_summary_df,
            use_container_width=True,
            hide_index=True,
        )

        csv_export_df = summary_df.drop(
            columns=["id"],
            errors="ignore",
        )

        csv_data = (
            csv_export_df
            .to_csv(index=False)
            .encode("utf-8-sig")
        )

        st.download_button(
            label="Genel durum tablosunu CSV olarak indir",
            data=csv_data,
            file_name=f"{selected_project['title']}_genel_durum_tablosu.csv",
            mime="text/csv",
            key=f"summary_csv_{selected_project_id}",
        )

    st.markdown("### Genel Durum Tablosundan Kanıtları Görüntüle")

    if summary_df.empty:
        st.info("Kanıt görüntülemek için önce iş kalemi eklenmelidir.")
    else:
        task_options = {}

        for _, row in summary_df.iterrows():
            label = (
                f"{row['İş Kalemi']} "
                f"— Durum: {status_badge(row['Durum'])} "
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
            task_id=selected_task_id,
            key_prefix="summary_area",
        )

    st.markdown("---")

    st.markdown("### İş Kalemlerini Güncelle ve Kanıt Dosyası Yükle")

    if raw_tasks_df.empty:
        st.info("Bu çalışmada henüz iş kalemi bulunmamaktadır.")
    else:
        for _, raw_row in raw_tasks_df.iterrows():
            task_id = int(raw_row["id"])
            evidence_count = get_evidence_count(task_id)

            expander_title = (
                f"{raw_row['task_name']} | "
                f"Durum: {status_badge(raw_row['status'])} | "
                f"Kanıt dosyası: {evidence_count}"
            )

            with st.expander(expander_title):
                st.markdown("#### İş Bilgileri")

                responsible_people = st.text_input(
                    "Kimler tarafından yapılacak / yapıldı?",
                    value=safe_text(raw_row["responsible_people"]),
                    key=f"responsible_{task_id}",
                )

                status = st.selectbox(
                    "İşin durumu",
                    STATUS_OPTIONS,
                    index=STATUS_OPTIONS.index(raw_row["status"])
                    if raw_row["status"] in STATUS_OPTIONS
                    else 0,
                    key=f"status_{task_id}",
                )

                start_date = st.text_input(
                    "Başlama tarihi",
                    value=safe_text(raw_row["start_date"]),
                    placeholder="Örn. 2026-04-25",
                    key=f"start_date_{task_id}",
                )

                due_date = st.text_input(
                    "Hedef tarih",
                    value=safe_text(raw_row["due_date"]),
                    placeholder="Örn. 2026-05-15",
                    key=f"due_date_{task_id}",
                )

                notes = st.text_area(
                    "Notlar",
                    value=safe_text(raw_row["notes"]),
                    key=f"notes_{task_id}",
                )

                col_update, col_delete = st.columns(2)

                with col_update:
                    if st.button(
                        "Bu iş kalemini güncelle",
                        key=f"update_task_{task_id}",
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
                        key=f"delete_task_{task_id}",
                    ):
                        delete_task(task_id)

                        st.warning(
                            "İş kalemi ve ona bağlı kanıt dosyaları silindi."
                        )
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
                        "PDF, Word, Excel, görsel, SPSS çıktısı veya "
                        "başka bir kanıt dosyası yükleyebilirsiniz."
                    ),
                )

                if st.button(
                    "Kanıt dosyalarını kaydet",
                    key=f"save_evidence_{task_id}",
                ):
                    if not uploaded_files:
                        st.warning("Önce en az bir dosya seçiniz.")
                    else:
                        try:
                            for uploaded_file in uploaded_files:
                                save_evidence_file(
                                    project_id=selected_project_id,
                                    task_id=task_id,
                                    uploaded_file=uploaded_file,
                                    evidence_note=evidence_note.strip(),
                                )

                            st.success("Kanıt dosyaları kaydedildi.")
                            st.rerun()

                        except Exception as error:
                            st.error("Kanıt dosyası yüklenemedi.")
                            st.caption(str(error))

                st.markdown("---")
                st.markdown("#### Bu İş Kalemine Ait Kayıtlı Kanıt Dosyaları")

                show_evidence_files(
                    task_id=task_id,
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
                project_id=selected_project_id,
                task_name=custom_task_name.strip(),
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
