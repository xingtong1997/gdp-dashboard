import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import plotly.express as px
import os
import ast # Pour parser la chaîne de liste de tuples en toute sécurité
import traceback # Pour afficher les erreurs de parsing détaillées

# --- Configuration de la Page ---
st.set_page_config(
    page_title="Walkability Analysis Dashboard",
    page_icon="🚶",
    layout="wide"
)

# --- Fonction de Parsing et Conversion des Coordonnées ---
def parse_and_convert_coordinates(coord_str):
    """
    Parse une chaîne représentant une liste de tuples (lon, lat)
    et la convertit en une liste de tuples (lat, lon).
    Retourne une liste vide en cas d'erreur.
    """
    if not isinstance(coord_str, str) or not coord_str.strip():
        return []
    try:
        # 1. Parser la chaîne en liste de tuples
        # Utilise ast.literal_eval pour la sécurité (évite l'exécution de code arbitraire)
        lon_lat_list = ast.literal_eval(coord_str)

        # 2. Vérifier si le résultat est une liste
        if not isinstance(lon_lat_list, list):
            st.warning(f"Format de coordonnées non reconnu (pas une liste): {coord_str[:100]}...")
            return []

        # 3. Convertir [(lon, lat), ...] en [(lat, lon), ...] et en float
        lat_lon_list = []
        for item in lon_lat_list:
            if isinstance(item, (list, tuple)) and len(item) == 2:
                try:
                    # Important : Conversion lon, lat -> lat, lon
                    lat = float(item[1])
                    lon = float(item[0])
                    lat_lon_list.append((lat, lon))
                except (ValueError, TypeError):
                    st.warning(f"Coordonnées non numériques dans le tuple: {item} dans {coord_str[:100]}...")
                    # Décider si on ignore juste ce point ou tout le segment
                    continue # Ignore ce point et passe au suivant
            else:
                 st.warning(f"Élément non conforme (pas un tuple/liste de 2) trouvé: {item} dans {coord_str[:100]}...")
                 # Décider si on ignore juste ce point ou tout le segment
                 continue # Ignore ce point

        return lat_lon_list

    except (SyntaxError, ValueError, TypeError) as e:
        st.error(f"Erreur de parsing de la chaîne de coordonnées: {coord_str[:100]}...")
        # Afficher l'erreur détaillée dans les logs ou en mode debug
        print(f"Erreur de parsing pour: {coord_str}")
        traceback.print_exc()
        return [] # Retourne une liste vide en cas d'échec

# --- Chargement des Données ---
@st.cache_data
def load_data(path_data_path, sensor_data_path):
    # Charger les données du chemin (nouveau format: id, "[(lon, lat),...]")
    processed_path_df = pd.DataFrame(columns=['segment_id', 'locations']) # Init df vide
    try:
        # Lire en spécifiant les noms de colonnes attendus
        path_df = pd.read_csv(path_data_path, names=['segment_id', 'coordinates_str'], header=None) # Lire sans en-tête, nommer les colonnes

        # S'assurer que segment_id est une chaîne
        path_df['segment_id'] = path_df['segment_id'].astype(str)
        # Remplacer les NaN potentiels dans coordinates_str par des chaînes vides
        path_df['coordinates_str'] = path_df['coordinates_str'].fillna('')


        st.write("Parsing segments coordinates...") # Feedback pour l'utilisateur

        # Appliquer la fonction de parsing
        # Note: parse_and_convert_coordinates retourne [] en cas d'erreur
        path_df['locations'] = path_df['coordinates_str'].apply(parse_and_convert_coordinates)

        # --- Section de rapport d'erreur améliorée ---
        # Identifier les lignes où le parsing a échoué (locations est une liste vide)
        # Exclure les lignes où la chaîne originale était déjà vide/NaN
        failed_parsing_mask = (path_df['locations'].apply(len) == 0) & (path_df['coordinates_str'].str.strip() != '')
        failed_parsing_df = path_df[failed_parsing_mask]

        if not failed_parsing_df.empty:
            st.error("Erreur de parsing des coordonnées pour les segments suivants :")
            # Afficher max 10 erreurs pour ne pas surcharger
            for index, row in failed_parsing_df.head(10).iterrows():
                st.error(f"  - Segment ID: {row['segment_id']}")
                # Afficher un extrait de la chaîne problématique
                st.code(f"    Données (extrait): {row['coordinates_str'][:200]}...")
            if len(failed_parsing_df) > 10:
                st.error(f"  ... et {len(failed_parsing_df) - 10} autres segments.")
        # --- Fin Section de rapport d'erreur ---

        # Filtrer les segments qui n'ont pas pu être parsés ou qui sont vides
        original_rows = len(path_df)
        processed_path_df = path_df[path_df['locations'].apply(len) > 0][['segment_id', 'locations']].copy() # Garde seulement les succès

        num_failed = len(failed_parsing_df)
        num_empty_original = original_rows - len(path_df[path_df['coordinates_str'].str.strip() != ''])
        num_successfully_parsed = len(processed_path_df)

        st.write(f"Parsing finished: {num_successfully_parsed} segments loaded successfully.")
        if num_failed > 0:
             st.warning(f"{num_failed} segments ignorés en raison d'erreurs de parsing.")
        # if num_empty_original > 0:
        #      st.info(f"{num_empty_original} lignes avaient des coordonnées vides à l'origine.")


    except FileNotFoundError:
        st.error(f"Erreur: Le fichier de chemin {path_data_path} n'a pas été trouvé.")
        # processed_path_df reste le df vide initialisé
    except Exception as e:
        st.error(f"Erreur lors du chargement ou du traitement de {path_data_path}: {e}")
        st.error(traceback.format_exc()) # Affiche l'erreur complète pour le débogage
        # processed_path_df reste le df vide initialisé

    # --- Chargement Sensor Data (inchangé) ---
    try:
        sensor_df = pd.read_csv(sensor_data_path)
        sensor_df['timestamp'] = pd.to_datetime(sensor_df['timestamp'])
        sensor_df['segment_id'] = sensor_df['segment_id'].astype(str)
    except FileNotFoundError:
        # st.warning(f"Le fichier de données capteurs {sensor_data_path} n'a pas été trouvé.")
        sensor_df = pd.DataFrame(columns=['segment_id', 'timestamp', 'latitude', 'longitude', 'irregularity_value', 'current_width', 'pedestrian_detected'])
    except Exception as e:
        st.error(f"Erreur lors du chargement de {sensor_data_path}: {e}")
        sensor_df = pd.DataFrame(columns=['segment_id', 'timestamp', 'latitude', 'longitude', 'irregularity_value', 'current_width', 'pedestrian_detected'])

    return processed_path_df, sensor_df

# --- Chemins vers vos fichiers CSV ---
PATH_CSV_PATH = 'segments.csv' # Votre fichier avec id, "[(lon, lat),...]"
SENSOR_CSV_PATH = 'sensor_data.csv' # Fichier optionnel avec données temporelles

path_df, sensor_df = load_data(PATH_CSV_PATH, SENSOR_CSV_PATH)

# --- Interface Utilisateur ---
st.title("📊 Walkability analysis dashboard")
st.markdown("Data visualization of sidewalk state and caracteristics")

if path_df.empty:
    st.warning("Impossible d'afficher la carte car les données du chemin n'ont pas pu être chargées ou parsées.")
    st.stop()

# --- Sélection du Segment ---
segment_options = ["Vue Générale"] + sorted(path_df['segment_id'].astype(int).unique().tolist())
selected_segment_id = st.sidebar.selectbox("Sélectionnez un Segment :", options=segment_options)

# --- Affichage Principal (Carte et Données) ---
col1, col2 = st.columns([2, 1])

with col1:
    st.subheader("🗺️ Robot's path map")

    m = folium.Map(location=[48.8566, 2.3522], zoom_start=12) # Centre/zoom par défaut

    # Ajuster la vue initiale aux limites de tous les points
    if not path_df.empty:
        all_lats = []
        all_lons = []
        # Itérer sur la colonne 'locations' qui contient des listes de (lat, lon)
        for loc_list in path_df['locations']:
            if loc_list: # Vérifier si la liste n'est pas vide
                 # Extraire les latitudes et longitudes de chaque tuple dans la liste
                 all_lats.extend([point[0] for point in loc_list]) # point[0] est la latitude
                 all_lons.extend([point[1] for point in loc_list]) # point[1] est la longitude

        if all_lats and all_lons: # S'assurer qu'on a collecté des points
            min_lat, max_lat = min(all_lats), max(all_lats)
            min_lon, max_lon = min(all_lons), max(all_lons)

            if min_lat != max_lat or min_lon != max_lon:
                 bounds = [[min_lat, min_lon], [max_lat, max_lon]]
                 m.fit_bounds(bounds, padding=(0.01, 0.01))
            else:
                 m.location = [min_lat, min_lon]
                 m.zoom_start = 16
        else:
            st.warning("Impossible de calculer les limites géographiques (pas de coordonnées valides après parsing).")
    else:
         st.warning("Données de chemin vides pour ajuster automatiquement la carte.")


    # Afficher tous les segments sur la carte
    if not path_df.empty:
        # Itérer sur les lignes du DataFrame traité
        for index, segment_row in path_df.iterrows():
            segment_id = segment_row['segment_id']
            locations = segment_row['locations'] # Récupère la liste de (lat, lon)

            if len(locations) >= 2: # Besoin d'au moins 2 points pour une ligne
                line_color = "#FF0000" if segment_id == selected_segment_id else "#007bff"
                line_weight = 10 if segment_id == selected_segment_id else 6

                folium.PolyLine(
                    locations=locations, # Utilise directement la liste de (lat, lon)
                    color=line_color,
                    weight=line_weight,
                    opacity=0.8,
                    tooltip=f"Segment ID: {segment_id}"
                ).add_to(m)
            elif len(locations) == 1:
                 folium.Marker(
                      location=locations[0],
                      tooltip=f"Segment ID: {segment_id} (point unique)",
                      icon=folium.Icon(color='gray', icon='info-sign')
                 ).add_to(m)

    # Afficher la carte
    map_data = st_folium(m, width='100%', height=500)

with col2:
    st.subheader("🔍 Segment's details")

    if selected_segment_id == "Vue Générale" or selected_segment_id is None:
        st.info("Select a segment in the drop-down menu on the left to display details.")
        # ... (code pour statistiques globales inchangé, peut nécessiter sensor_df) ...
        st.markdown("---")
        st.subheader("Global statistics")
        if not sensor_df.empty:
             st.metric("Number of segments", path_df['segment_id'].nunique())
             if 'current_width' in sensor_df.columns:
                 st.metric("Sidewalk mean width (m)", f"{sensor_df['current_width'].mean():.2f}")
             if 'irregularity_value' in sensor_df.columns:
                 st.metric("Max number of irregularities in one segment", f"{sensor_df['irregularity_value'].max():.2f}")
        else:
             st.metric("Nombre total de segments", path_df['segment_id'].nunique())
             st.warning("Données capteurs ('sensor_data.csv') non disponibles pour statistiques globales détaillées.")

    # Le reste de la logique pour afficher les détails (graphiques, etc.)
    # reste basé sur sensor_df et selected_segment_id.
    # Il faut s'assurer que le fichier sensor_data.csv existe et
    # contient une colonne 'segment_id' qui correspond aux IDs dans segments.csv

    elif not sensor_df.empty:
        segment_data = sensor_df[sensor_df['segment_id'] == selected_segment_id].copy()

        if not segment_data.empty:
            st.markdown(f"**Segment ID : {selected_segment_id}**")
            # ... (affichage des métriques et graphiques basé sur segment_data) ...
            col_metric1, col_metric2 = st.columns(2)
            with col_metric1:
                metric_val = segment_data['current_width'].mean()
                st.metric("Mean width (m)", f"{metric_val:.2f}" if pd.notna(metric_val) else "N/A")
            with col_metric2:
                metric_val = segment_data['irregularity_value'].max()
                st.metric("Max irregularity", f"{metric_val:.2f}" if pd.notna(metric_val) else "N/A")

            st.markdown("---")
            st.markdown("**Temporal data charts :**")

            # Graphique : Irrégularité
            if 'irregularity_value' in segment_data.columns and segment_data['irregularity_value'].notna().any():
                fig_irreg = px.line(segment_data.sort_values('timestamp'), x='timestamp', y='irregularity_value', title='Evolution de l\'irrégularité', labels={'timestamp': 'Temps', 'irregularity_value': 'Indice d\'irrégularité'})
                fig_irreg.update_layout(xaxis_title=None, yaxis_title="Irrégularité")
                st.plotly_chart(fig_irreg, use_container_width=True)

            # Graphique : Largeur
            if 'current_width' in segment_data.columns and segment_data['current_width'].notna().any():
                fig_width = px.line(segment_data.sort_values('timestamp'), x='timestamp', y='current_width', title='Evolution de la largeur', labels={'timestamp': 'Temps', 'current_width': 'Largeur (m)'})
                fig_width.update_layout(xaxis_title=None, yaxis_title="Largeur (m)")
                st.plotly_chart(fig_width, use_container_width=True)

            # Graphique : Passants
            if 'pedestrian_detected' in segment_data.columns and segment_data['pedestrian_detected'].notna().any():
                 segment_data['pedestrian_detected'] = segment_data['pedestrian_detected'].astype(int)
                 if segment_data['pedestrian_detected'].sum() > 0:
                    pedestrian_summary = segment_data.resample('T', on='timestamp')['pedestrian_detected'].sum().reset_index(name='detections')
                    pedestrian_summary = pedestrian_summary[pedestrian_summary['detections'] > 0]
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
            st.markdown(f"**Segment ID : {selected_segment_id}**")
            st.info(f"Aucune donnée détaillée (capteurs) trouvée pour le segment {selected_segment_id} dans '{SENSOR_CSV_PATH}'.")
            # Afficher les points du chemin pour référence
            segment_path_row = path_df[path_df['segment_id'] == selected_segment_id].iloc[0]
            if segment_path_row is not None and segment_path_row['locations']:
                 st.markdown("**Points du chemin (Lat, Lon) pour ce segment :**")
                 # Afficher les points sous forme de DataFrame pour la clarté
                 points_df = pd.DataFrame(segment_path_row['locations'], columns=['Latitude', 'Longitude'])
                 st.dataframe(points_df)

    else:
         st.warning(f"Le fichier de données capteurs '{SENSOR_CSV_PATH}' est vide ou n'a pas pu être chargé. Impossible d'afficher les détails du segment.")