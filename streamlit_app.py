
import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium # Pour une meilleure intégration et interaction potentielle
import plotly.express as px
import os # Pour gérer les chemins de fichiers

# --- Configuration de la Page ---
st.set_page_config(
    page_title="Dashboard Analyse Trottoirs",
    page_icon="🚶",
    layout="wide" # Utilise toute la largeur de la page
)

# --- Chargement des Données ---
# Utilisez st.cache_data pour éviter de recharger les données à chaque interaction
@st.cache_data
def load_data(segments_path, sensor_data_path):
    try:
        segments_df = pd.read_csv(segments_path)
        # S'assurer que segment_id est du bon type (ex: string pour éviter les problèmes)
        segments_df['segment_id'] = segments_df['segment_id'].astype(str)
    except FileNotFoundError:
        st.error(f"Erreur: Le fichier {segments_path} n'a pas été trouvé.")
        # Créer un DataFrame vide pour éviter les erreurs suivantes
        segments_df = pd.DataFrame(columns=['segment_id', 'start_lat', 'start_lon', 'end_lat', 'end_lon'])
    except Exception as e:
        st.error(f"Erreur lors du chargement de {segments_path}: {e}")
        segments_df = pd.DataFrame(columns=['segment_id', 'start_lat', 'start_lon', 'end_lat', 'end_lon'])

    try:
        sensor_df = pd.read_csv(sensor_data_path)
        # Convertir la colonne timestamp en datetime
        sensor_df['timestamp'] = pd.to_datetime(sensor_df['timestamp'])
        # S'assurer que segment_id est du même type que dans segments_df
        sensor_df['segment_id'] = sensor_df['segment_id'].astype(str)
    except FileNotFoundError:
        st.error(f"Erreur: Le fichier {sensor_data_path} n'a pas été trouvé.")
        # Créer un DataFrame vide
        sensor_df = pd.DataFrame(columns=['segment_id', 'timestamp', 'latitude', 'longitude', 'irregularity_value', 'current_width', 'pedestrian_detected'])
    except Exception as e:
        st.error(f"Erreur lors du chargement de {sensor_data_path}: {e}")
        sensor_df = pd.DataFrame(columns=['segment_id', 'timestamp', 'latitude', 'longitude', 'irregularity_value', 'current_width', 'pedestrian_detected'])

    return segments_df, sensor_df

# --- Chemins vers vos fichiers CSV ---
# !! Important : Adaptez ces chemins si nécessaire !!
# Par défaut, cherche les fichiers dans le même dossier que le script :
SEGMENTS_CSV_PATH = 'segments.csv'
SENSOR_CSV_PATH = 'sensor_data.csv'

segments_df, sensor_df = load_data(SEGMENTS_CSV_PATH, SENSOR_CSV_PATH)

# --- Interface Utilisateur ---
st.title("📊 Dashboard d'Analyse des Trottoirs")
st.markdown("Visualisation des données collectées par le robot sur l'état des trottoirs.")

# Vérifier si les dataframes sont vides (erreur de chargement)
if segments_df.empty:
    st.warning("Impossible d'afficher la carte car les données des segments n'ont pas pu être chargées.")
    st.stop() # Arrête l'exécution du script ici

# --- Sélection du Segment ---
# On utilise une liste déroulante pour sélectionner le segment.
segment_options = ["Vue Générale"] + sorted(segments_df['segment_id'].unique().tolist())
selected_segment_id = st.sidebar.selectbox("Sélectionnez un Segment :", options=segment_options)

# --- Affichage Principal (Carte et Données) ---
col1, col2 = st.columns([2, 1]) # Carte plus large que les détails

with col1:
    st.subheader("🗺️ Carte du Parcours")

    # Créer la carte Folium
    if not segments_df.empty:
        map_center = [segments_df['start_lat'].mean(), segments_df['start_lon'].mean()]
    else:
        map_center = [48.8566, 2.3522] # Centre par défaut (Paris)

    m = folium.Map(location=map_center, zoom_start=15)

    # Afficher tous les segments
    for _, segment in segments_df.iterrows():
        locations = [
            (segment['start_lat'], segment['start_lon']),
            (segment['end_lat'], segment['end_lon'])
        ]
        line_color = "#FF0000" if segment['segment_id'] == selected_segment_id else "#007bff"
        line_weight = 15 if segment['segment_id'] == selected_segment_id else 10

        folium.PolyLine(
            locations=locations,
            color=line_color,
            weight=line_weight,
            opacity=0.8,
            tooltip=f"Segment ID: {segment['segment_id']}"
        ).add_to(m)

    # Afficher la carte
    map_data = st_folium(m, width='100%', height=500)

with col2:
    st.subheader("🔍 Détails du Segment")

    if selected_segment_id == "Vue Générale" or selected_segment_id is None:
        st.info("Sélectionnez un segment dans la liste à gauche pour afficher ses détails.")
        st.markdown("---")
        st.subheader("Statistiques Globales")
        if not segments_df.empty:
            st.metric("Nombre total de segments", segments_df.shape[0])
            if 'avg_width' in segments_df.columns and segments_df['avg_width'].notna().any():
                 st.metric("Largeur moyenne globale (m)", f"{segments_df['avg_width'].mean():.2f}")
            if 'max_irregularity' in segments_df.columns and segments_df['max_irregularity'].notna().any():
                 st.metric("Irrégularité max rencontrée", f"{segments_df['max_irregularity'].max():.2f}")
        else:
            st.warning("Données globales non disponibles.")

    elif not sensor_df.empty:
        segment_data = sensor_df[sensor_df['segment_id'] == selected_segment_id].copy()
        segment_details = segments_df[segments_df['segment_id'] == selected_segment_id].iloc[0] if not segments_df[segments_df['segment_id'] == selected_segment_id].empty else None

        if not segment_data.empty:
            st.markdown(f"**Segment ID : {selected_segment_id}**")

            # Afficher des métriques clés
            col_metric1, col_metric2 = st.columns(2)
            with col_metric1:
                metric_val = segment_details['avg_width'] if segment_details is not None and 'avg_width' in segment_details and pd.notna(segment_details['avg_width']) else segment_data['current_width'].mean()
                st.metric("Largeur Moyenne (m)", f"{metric_val:.2f}" if pd.notna(metric_val) else "N/A")
            with col_metric2:
                metric_val = segment_details['max_irregularity'] if segment_details is not None and 'max_irregularity' in segment_details and pd.notna(segment_details['max_irregularity']) else segment_data['irregularity_value'].max()
                st.metric("Irrégularité Max", f"{metric_val:.2f}" if pd.notna(metric_val) else "N/A")

            st.markdown("---")
            st.markdown("**Graphiques des Données Temporelles**")


            # Graphique : Irrégularité
            if 'irregularity_value' in segment_data.columns and segment_data['irregularity_value'].notna().any():
                # Correction: Mise sur une seule ligne logique pour éviter les problèmes de syntaxe multi-lignes
                fig_irreg = px.line(segment_data.sort_values('timestamp'), x='timestamp', y='irregularity_value', title='Evolution de l\'irrégularité', labels={'timestamp': 'Temps', 'irregularity_value': 'Indice d\'irrégularité'})
                
                fig_irreg.update_layout(xaxis_title=None, yaxis_title="Irrégularité")
                st.plotly_chart(fig_irreg, use_container_width=True)

            # Graphique : Largeur
            if 'current_width' in segment_data.columns and segment_data['current_width'].notna().any():
                fig_width = px.line(segment_data.sort_values('timestamp'), x='timestamp', y='current_width',
                                    title='Evolution de la largeur', labels={'timestamp': 'Temps', 'current_width': 'Largeur (m)'})
                fig_width.update_layout(xaxis_title=None, yaxis_title="Largeur (m)")
                st.plotly_chart(fig_width, use_container_width=True)

            # Graphique : Passants
            if 'pedestrian_detected' in segment_data.columns and segment_data['pedestrian_detected'].notna().any():
                 segment_data['pedestrian_detected'] = segment_data['pedestrian_detected'].astype(int)
                 if segment_data['pedestrian_detected'].sum() > 0: # S'il y a eu des détections
                    pedestrian_summary = segment_data.resample('T', on='timestamp')['pedestrian_detected'].sum().reset_index(name='detections')
                    pedestrian_summary = pedestrian_summary[pedestrian_summary['detections'] > 0] # Ne garder que les minutes avec détection
                    fig_ped = px.bar(pedestrian_summary, x='timestamp', y='detections', title='Détections de passants par minute')
                    fig_ped.update_layout(xaxis_title=None, yaxis_title="Nb Détections")
                    st.plotly_chart(fig_ped, use_container_width=True)
                 else:
                     st.markdown("*Aucun passant détecté sur ce segment.*")


            # Données brutes
            st.markdown("---")
            st.markdown("**Données Brutes (échantillon)**")
            st.dataframe(segment_data.head())

        else:
            st.warning(f"Aucune donnée détaillée trouvée pour le segment {selected_segment_id}.")
    else:
         st.warning("Les données des capteurs n'ont pas pu être chargées.")

