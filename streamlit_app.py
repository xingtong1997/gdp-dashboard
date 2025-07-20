import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import plotly.express as px
import os
import ast #To safely parse string representations of Python literals (like lists of tuples).
import traceback #To display detailed error information for debugging.
import json
import plotly.graph_objects as go
import datetime


#Json files importation
with open("data/irr_event_coordinates.json", mode="r", encoding="utf-8") as irr_event_coordinates:
    irr_event_coordinates = json.load(irr_event_coordinates)
with open("data/ped_density_per_segment.json", mode="r", encoding="utf-8") as ped_density_per_segment:
    ped_density_per_segment = json.load(ped_density_per_segment)
with open("data/ped_speed_per_segment.json", mode="r", encoding="utf-8") as ped_speed_per_segment:
    ped_speed_per_segment = json.load(ped_speed_per_segment)
with open("data/slope_per_segment.json", mode="r", encoding="utf-8") as slope_per_segment:
    slope_per_segment = json.load(slope_per_segment)
with open("data/width_per_segment.json", mode="r", encoding="utf-8") as width_per_segment:
    width_per_segment = json.load(width_per_segment)

# --- Setting up page configuration ---
st.set_page_config(
    page_title="Walkability Analysis Dashboard",
    page_icon="🚶",
    layout="wide"
)

# --- Function to Parse and Convert Coordinates. ---
def parse_and_convert_coordinates(coord_str):
    """
    Parses a string representing a list of (lon, lat) tuples and converts it to a list of (lat, lon) tuples. Returns an empty list on error.
    """
    if not isinstance(coord_str, str) or not coord_str.strip():
        return []
    try:
        # 1. Parse the string into a list of tuples using ast.literal_eval for safety (avoids arbitrary code execution).
        
        lon_lat_list = ast.literal_eval(coord_str)

        # 2. Verify that the result is a list.
        if not isinstance(lon_lat_list, list):
            st.warning(f"Unrecognized coordinate format (not a list): {coord_str[:100]}...")
            return []

        # 3. Convert [(lon, lat), ...] to [(lat, lon), ...] and to float type.
        lat_lon_list = []
        for item in lon_lat_list:
            if isinstance(item, (list, tuple)) and len(item) == 2:
                try:
                    # Important : Convert lon, lat -> lat, lon
                    lat = float(item[1])
                    lon = float(item[0])
                    lat_lon_list.append((lat, lon))
                except (ValueError, TypeError):
                    st.warning(f"Non-numeric coordinates in tuple: {item} in {coord_str[:100]}...")
                    # Handle cases where coordinates are not numeric.
                    continue 
            else:
                 st.warning(f"Non-compliant element (not a tuple/list of 2) found: {item} in  {coord_str[:100]}...")
                 #Handle non-compliant elements (not a tuple/list of 2).
                 continue 

        return lat_lon_list

    except (SyntaxError, ValueError, TypeError) as e:
        st.error(f"Error parsing coordinate string: {coord_str[:100]}...")
        # Print the detailed error for debugging purposes.
        print(f"Parsing error for: {coord_str}")
        traceback.print_exc()
        return [] # Returns an empty list on failure.

# --- Data Loading Function. ---
@st.cache_data
def load_data(path_data_path, unevenness_irregularity_per_segment_path):
    # Initialize an empty DataFrame for the processed path data.
    processed_path_df = pd.DataFrame(columns=['segment_id', 'locations'])
    try:
        # Read the CSV file, specifying column names and no header.
        path_df = pd.read_csv(path_data_path, names=['segment_id', 'coordinates_str'], header=None) 

        # Ensure segment_id is a string type.
        path_df['segment_id'] = path_df['segment_id'].astype(str)
        # Replace potential NaN values in coordinates_str with empty strings.
        path_df['coordinates_str'] = path_df['coordinates_str'].fillna('')


        #st.write("Parsing segments coordinates...") # User Feedback

        # Apply the parsing function to the coordinates string column.

        path_df['locations'] = path_df['coordinates_str'].apply(parse_and_convert_coordinates)

        # --- Enhanced Error Reporting Section. ---
        # Identify rows where parsing failed (locations is an empty list) but the original string was not empty.
        failed_parsing_mask = (path_df['locations'].apply(len) == 0) & (path_df['coordinates_str'].str.strip() != '')
        failed_parsing_df = path_df[failed_parsing_mask]

        if not failed_parsing_df.empty:
            st.error("Coordinates parsing error for the following segments :")
            # Display a maximum of 10 errors to avoid cluttering the UI.
            for index, row in failed_parsing_df.head(10).iterrows():
                st.error(f"  - Segment ID: {row['segment_id']}")
                # Display an excerpt of the problematic string.
                st.code(f"    Data: {row['coordinates_str'][:200]}...")
            if len(failed_parsing_df) > 10:
                st.error(f"  ... and {len(failed_parsing_df) - 10} other segments")
        # --- End of Error Reporting Section. ---

        # Filter out segments that could not be parsed or were originally empty.
        original_rows = len(path_df)
        processed_path_df = path_df[path_df['locations'].apply(len) > 0][['segment_id', 'locations']].copy() 

        num_failed = len(failed_parsing_df)
        num_empty_original = original_rows - len(path_df[path_df['coordinates_str'].str.strip() != ''])
        num_successfully_parsed = len(processed_path_df)

        #st.write(f"Parsing finished: {num_successfully_parsed} segments loaded successfully.") User Feedback
        if num_failed > 0:
             st.warning(f"{num_failed} ignored segments due to parsing errors")


    except FileNotFoundError:
        st.error(f"Error: The file path {path_data_path} was not found")
        # processed_path_df remains the initialized empty df
    except Exception as e:
        st.error(f"Error while loading or processing  {path_data_path}: {e}")
        st.error(traceback.format_exc()) # isplays the full error for debugging.
        # processed_path_df remains the initialized empty df

    try:
        unevenness_irregularity_per_segment_df = pd.read_csv(unevenness_irregularity_per_segment_path)
    except FileNotFoundError:
        unevenness_irregularity_per_segment_df = pd.DataFrame(columns=['segment_id', 'average_unevenness_index', 'average_irregularity_index'])
    return processed_path_df, unevenness_irregularity_per_segment_df

  # ---
  # Function to Process Pedestrian Data.
  # ---
def process_pedestrian_data_per_quarter_hour(file_path):
    """
    Loads pedestrian detection data, aggregates it by quarter-hour, and counts unique pedestrians.

    Args:
        file_path (str): Path to the CSV file. The CSV must have 'timestamp' 
                        and 'pedestrian_ids' columns. 'pedestrian_ids' must 
                        be a string representing a list of IDs, e.g., "[101, 102, 103]".

    Returns:
        pandas.DataFrame: A DataFrame with 'timestamp_quarter' 
                        (start of the quarter-hour) and 'unique_pedestrian_count' 
                        columns. Returns an empty DataFrame on error.
    """
    try:
        df = pd.read_csv(file_path, sep=';')

        # Check for required columns.
        if 'time_rounded' not in df.columns or 'persons' not in df.columns:
            # In Streamlit, one would use st.error(); outside Streamlit, print() or raise an exception.
            print(f"Error: The CSV file '{file_path}' must contains the columns 'time_rund' and 'persons'.")
            return pd.DataFrame(columns=['timestamp_quarter', 'unique_pedestrian_count'])

        # 1. Convert the 'timestamp' column to datetime objects and floor to the nearest 15 minutes.
        df['time_rounded'] = pd.to_datetime(df['time_rounded'], format="%H:%M")
        df['time_rounded'] = df['time_rounded'].dt.floor('15min').dt.time
        # 2. Parse the 'pedestrian_ids' column (string) into Python lists of IDs.
        def parse_id_list_from_string(id_list_str):
            if pd.isna(id_list_str) or not isinstance(id_list_str, str) or not id_list_str.strip():
                return [] # Returns an empty list if the string is empty, NaN, or not a string.
            try:
                ids = ast.literal_eval(id_list_str)
                # Ensure it's a list and the IDs are, for example, integers.
                if isinstance(ids, list):
                    return [int(pid) for pid in ids] # or str(pid) if your IDs are strings
                return []
            except (ValueError, SyntaxError, TypeError):
                # Handle malformed strings.
                return []
        
        df['parsed_ids'] = df['persons'].apply(parse_id_list_from_string)

        # 3. Set 'timestamp' as the index for the resample function.
        df = df.set_index('time_rounded')

        # 4. & 5. Group by quarter-hour ('15T') and aggregate.
        def aggregate_unique_ids(series_of_lists_of_ids):
            # series_of_lists_of_ids contains all 'parsed_ids' lists for a given quarter-hour.
            if series_of_lists_of_ids.empty:
                return 0
             
            combined_list = []
            for id_list in series_of_lists_of_ids:
                combined_list.extend(id_list) # Concatenate all lists
            
            if not combined_list:
                return 0
            
            #unique_ids = set(combined_list) # Remove duplicates if wanted
            return len(combined_list)         # Count
        
        # 6. Group by the provided quarter-hour column.
        quarter_hour_summary = df.groupby(['segment_id','time_rounded'])['parsed_ids'].apply(aggregate_unique_ids)

        # Rename the resulting series and convert it to a DataFrame.
        quarter_hour_summary_df = quarter_hour_summary.rename('unique_pedestrian_count').reset_index()
        quarter_hour_summary_df.rename(columns={'time_rounded': 'timestamp_quarter'}, inplace=True)

        # Ensure the results are sorted by time for plotting.
        quarter_hour_summary_df = quarter_hour_summary_df.sort_values(by=['segment_id','timestamp_quarter'])
        return quarter_hour_summary_df

    except FileNotFoundError:
        print(f"Error: File not found here: '{file_path}'.")
        return pd.DataFrame(columns=['timestamp_quarter', 'unique_pedestrian_count'])
    except Exception as e:
        print(f"An error has ocurred during the file processing {e}")
        # For more detailed debugging in a development environment:
        # import traceback
        # traceback.print_exc()
        return pd.DataFrame(columns=['timestamp_quarter', 'unique_pedestrian_count'])


# --- Paths to your CSV files. ---
PATH_CSV_PATH = 'data/segments.csv' # Your file with id, "[(lon, lat),...]".
UNEVENNESS_IRREGULARITY_PER_SEGMENT_PATH = 'data/unevenness_irregularity_per_segment.csv'
CHEMIN_FICHIER_PASSANTS = 'data/ExperimentData_quentin.csv'

path_df, unevenness_irregularity_per_segment_df = load_data(PATH_CSV_PATH, UNEVENNESS_IRREGULARITY_PER_SEGMENT_PATH)
Pedestrian_df = process_pedestrian_data_per_quarter_hour(CHEMIN_FICHIER_PASSANTS)

# --- User Interface. ---
st.title("📊 Sidewalk Mobility Data Dashboard")
st.markdown("Data visualization of sidewalk usage and caracteristics")

if path_df.empty:
    st.warning("Unable to display map due to path data unable to be processed or loaded.")
    st.stop()

# --- Segment Selection. ---
unique_ids_str = path_df['segment_id'].unique().tolist()

# Define a key function for robust numerical sorting (handles integers and potentially floats).
def robust_num_key(item_str):
    try:
        # Try converting to float for comparison (handles integers and decimals).
        return float(item_str)
    except ValueError:
        return float('inf')

# Sort the string IDs using the numerical key.
sorted_ids = sorted(unique_ids_str, key=robust_num_key)

# Create two tabs, the first for Data and the second for Project details.
tab1, tab2 = st.tabs(["# Data", "# Project Background"])



# Data display tab.
with tab1 :

    # --- Main Display (Map and Data). ---
    col_map, col_data = st.columns([1,1.3], border=True)

    with col_map:
        
        # Create options for the selectbox.
        segment_options = ["Overview"] + sorted_ids # Use the numerically sorted list.

        selected_segment_id = st.selectbox("Select a segment to display infos :", options=segment_options)
        

        ids_for_colors = sorted_ids

        # Colors from https://colorbrewer2.org/#type=qualitative&scheme=Paired&n=10
        color_palette = ['#a83500','#1f78b4','#50b800','#0a6100','#7d4c2c','#e31a1c','#129778','#ff7f00','#781297','#6a3d9a']
        num_colors = len(color_palette)

        # Create a dictionary mapping each segment_id to a color.
        segment_color_map = {}
        for i, seg_id in enumerate(ids_for_colors):
            # Assign colors cyclically if there are more IDs than colors.
            color_index = i % num_colors
            segment_color_map[seg_id] = color_palette[color_index]

        test = st.pills("test", "Display segments number", label_visibility="collapsed")

        st.subheader("🗺️ Studied Sidewalk Network")

        map_center = [59.346639,18.072167]

        m = folium.Map(location=map_center, zoom_start=16) # Default center/zoom.

        # Display all segments on the map.
        if not path_df.empty:
            # Iterate over the rows of the processed DataFrame.
            for index, segment_row in path_df.iterrows():
                segment_id = segment_row['segment_id']
                locations = segment_row['locations'] # Get the list of (lat, lon).

                if len(locations) >= 2: 
                    line_color = "#FF0000" if segment_id == selected_segment_id else "#007bff"
                    if selected_segment_id == "Overview" : 
                        line_color = segment_color_map.get(segment_id, '#808080') # Gray if ID not found.
                    line_weight = 10 if segment_id == selected_segment_id else 6
                    if test == "Display segments number":
                        folium.PolyLine(
                            locations=locations, 
                            color=line_color,
                            weight=line_weight,
                            opacity=0.8,
                            tooltip=folium.Tooltip(
                                f"{segment_id}", 
                                permanent=True,   
                                direction='center', 
                                sticky=False,     
                                opacity=0.7,      
                            )
                        ).add_to(m)
                    else : 
                        folium.PolyLine(
                            locations=locations, 
                            color=line_color,
                            weight=line_weight,
                            opacity=0.8,
                            tooltip=f"Segment ID: {segment_id}"
                        ).add_to(m)
                        
                elif len(locations) == 1:
                    folium.Marker(
                        location=locations[0],
                        tooltip=f"Segment ID: {segment_id} (single point)",
                        icon=folium.Icon(color='gray', icon='info-sign')
                    ).add_to(m)

        # Display map
        map_data = st_folium(m, width='100%', height=600)

    with col_data:

        st.subheader("🔍 Segment's details")

        if selected_segment_id == "Overview":

            st.info("Select a segment in the drop-down menu on the left to display details.")

            
            tab_unirreg, tab_abslop, tab_pedestrian = st.tabs(["Unvenness and irregularity indices","Absolute slope","Pedestrian data"])
            
            with tab_unirreg:

                #col_graph, col_details = st.columns([1, 0.5], border=True)
                #with col_graph:
                    st.subheader("Indices of unevenness and irregularity across sidewalks (excluding crossings)")

                    # --- Creation of the Figure with Two Y-Axes. ---
                    fig_combined = go.Figure()
                    # 1. Add the trace for Unevenness (Primary Y-Axis - Left).
                    fig_combined.add_trace(go.Scatter(
                        x=unevenness_irregularity_per_segment_df['segment_id'],
                        y=unevenness_irregularity_per_segment_df['average_unevenness_index'],
                        name='Unevenness', 
                        yaxis='y1',         
                        line=dict(color='royalblue') 
                    ))

                    # 2. Add the trace for Irregularity (Secondary Y-Axis - Right).
                    fig_combined.add_trace(go.Scatter(
                        x=unevenness_irregularity_per_segment_df['segment_id'],
                        y=unevenness_irregularity_per_segment_df['average_irregularity_index'],
                        name='irregularity', 
                        yaxis='y2',        
                        line=dict(color='darkorange') 
                    ))

                    # 3. Configure the Layout (Titles, Axes, dynamic range).
                    fig_combined.update_layout(
                        xaxis_title="segment id",
                        # Primary Y-Axis Configuration (Left) for Unevenness.
                        yaxis=dict(
                            title="unevenness",
                            
                            tickfont=dict(color="royalblue"),
                            side='left', # Position on the left.
                            range=[0, 1],
                            showgrid=False
                        ),
                        # Secondary Y-Axis Configuration (Right) for Irregularity.
                        yaxis2=dict(
                            title="irregularity",
                            tickfont=dict(color="darkorange"),
                            side='right',       # Position on the right.
                            overlaying="y",    # Overlay on the main Y-axis (shares the X-axis).
                        ),
                        legend=dict(x=0.1, y=1.1, orientation="h"), 
                        margin=dict(l=50, r=50, t=80, b=50) 
                    )

                    # Display the combined chart.
                    st.plotly_chart(fig_combined, use_container_width=True)
                
                #with col_details:
                    st.subheader("Graph explanation")
                    st.text("The graph illustrates the indices of unevenness and irregularity across nine sidewalk segments, with the irregularity events marked as red points. The unevenness index, which ranges from 0 to 1, remains relatively consistent across most segments. Segment 1 shows the highest unevenness, primarily due to the presence of broken and uneven bricks.")


            with tab_abslop:

                #col_graph, col_details = st.columns([1, 0.5], border=True)

                #with col_graph:

                    st.subheader("Absolute slope across segments")
                    Graph_color="royalblue"
                    fig_abslop = px.line(slope_per_segment, x='segment id', y='absolute slope', labels={'segment id': 'segment id', 'absolute slope': 'absolute slope'})
                    fig_abslop.update_traces(line_color=Graph_color)
                    fig_abslop.update_layout(
                        xaxis=dict(
                        title="Segment id",
                        tickfont=dict(color=Graph_color),
                        tickvals= [i for i in range (11)],
                        range=[0, 10]
                    ),
                    
                    yaxis=dict(
                        title="Absolute slope",
                        tickfont=dict(color=Graph_color),
                        side='left', # Position on the left
                        range=[0, 0.07]
                    )
                    )
                    st.plotly_chart(fig_abslop, use_container_width=True)

                #with col_details:
                    st.subheader("Graph explanation")
                    st.text("This graph describe the absolute slope values across the sidewalks. It represents the steepness of each segment regardless of direction. The highest absolute slope is observed at Segment 7. Segment 1 and 2 exhibit the lowest slope values. This measurement can well reflect the varying elevation characteristics of different sidewalks, which is important for evaluating walkability or planning sidewalk robot navigation.")
            
            with tab_pedestrian:
                fig_passants = go.Figure()
                pedestrian_overview = Pedestrian_df.groupby('timestamp_quarter')['unique_pedestrian_count'].sum()
                pedestrian_overview = pedestrian_overview.rename('total_pedestrian').reset_index()
                #st.dataframe(pedestrian_overview)
                fig_passants.add_trace(go.Bar(
                    x=pedestrian_overview['timestamp_quarter'],
                    y=pedestrian_overview['total_pedestrian'],
                    name='Number of pedestrian',
                    marker_color='rgb(26, 118, 255)' 
                    ))
                fig_passants.update_layout(
                        title_text="Pedestrians count along the day",
                        xaxis_title="Time of day",
                        yaxis_title="Number of pedestrian detected",
                        bargap=0.2, # space between the bars
                        
                    )
                st.plotly_chart(fig_passants, use_container_width=True)

        

        else :
            
            tab_data,tab_graph = st.tabs(["Detailed data and explanation","Pedestrian graph"])

            with tab_data:
                if 0<int(selected_segment_id)<10:

                    st.metric("Segment's number :", selected_segment_id)
                    with st.popover("Average pedestrian density :"):
                        st.markdown("The estimation of sidewalk pedestrian density is based on the three-dimensional pedestrian timespace diagram proposed by Saberi and Mahmassani (2014), which extends Edie’s definitions of fundamental traffic variables(Edie, 1963).")
                    st.metric("Average pedestrian density :", str(round(ped_density_per_segment[int(selected_segment_id)-1]["average pedestrian density"],3))+" ped/m\u00b2",label_visibility="collapsed")
                    with st.popover("Maximum pedestrian density :"):
                        st.markdown("The estimation of sidewalk pedestrian density is based on the three-dimensional pedestrian timespace diagram proposed by Saberi and Mahmassani (2014), which extends Edie’s definitions of fundamental traffic variables(Edie, 1963).")
                    st.metric("Maximum pedestrian density :", str(round(ped_density_per_segment[int(selected_segment_id)-1]["maximum pedestrian density"],3))+" ped/m\u00b2",label_visibility="collapsed")
                    with st.popover("Average pedestrian speed :"):
                        st.markdown("This feature represents the average speed of all pedestrians detected by the robot while traversing the given segment.")
                    st.metric("## Average pedestrian speed :", str(round(ped_speed_per_segment[int(selected_segment_id)-1]["average pedestrian speed"],3))+" m/s",label_visibility="collapsed")
                    
                    st.metric("Average effective width :", str(round(width_per_segment[int(selected_segment_id)-1]["average effective width"],3))+" m")
                    
                    st.metric("Average minimum effective width :", str(round(width_per_segment[int(selected_segment_id)-1]["average minimum effective width"],3))+" m")

                else:
                    st.info("No data is available for this specific segment")
            
            with tab_graph:
                st.subheader("Pedestrian count over the day on the selected segment")
                
                if Pedestrian_df.empty:
                    st.warning("No pedestrian data to display. Please verify the CSV file or the errors")
                else:
                    # Display the combined chart.
                    fig_passants = go.Figure()
                    # Add the main trace for the bars (all data for the day).
                    fig_passants.add_trace(go.Bar(
                        x=Pedestrian_df.loc[Pedestrian_df['segment_id'] == int(selected_segment_id)]['timestamp_quarter'],
                        y=Pedestrian_df.loc[Pedestrian_df['segment_id'] == int(selected_segment_id)]['unique_pedestrian_count'],
                        name='Number of pedestrian',
                        marker_color='rgb(26, 118, 255)' 
                    ))

                    # Configure the chart layout.
                    fig_passants.update_layout(
                        title_text="Pedestrians count along the day",
                        xaxis_title="Time of day",
                        yaxis_title="Number of pedestrian detected",
                        bargap=0.2, # space between bars
                        
                    )
                    st.plotly_chart(fig_passants, use_container_width=True)


        
# Project details display tab.
with tab2 :

    st.subheader("Investigating Sidewalks’ Mobility and Improving it with Robots (ISMIR)” Project")
    st.markdown("Sidewalk delivery robots offer a promising solution for sustainable City Logistics. These robots can be deployed from hubs, retail locations, or even retrofitted vehicles to perform short-range deliveries, partially replacing traditional, less sustainable methods. The ISMIR project aims to develop a deeper, data-driven understanding of sidewalk robot operations in realistic urban settings and to explore sidewalk mobility through the lens of robotic navigation.")
    st.markdown("ISMIR is a collaborative project involving researchers from [The Division of Transport and Systems Analysis](https://www.kth.se/en/som/avdelningar/sek/transport-och-systemanalys-1.17211) and the [Integrated Transport Research Lab (ITRL)](https://www.itrl.kth.se/integrated-transport-research-lab-itrl-1.1081637)  at KTH Royal Institute of Technology (Stockholm, Sweden).")
    st.markdown("The Investigating Sidewalks’ Mobility and Improving it with Robots (ISMIR)” project was funded by [Digital Futures](https://www.digitalfutures.kth.se/project/investigating-sidewalks-mobility-and-improving-it-with-robots-ismir/) and was carried out between 2023 and 2025.")
    
    st.markdown("##### Objective")
    st.markdown("Using empirical data from sidewalk robot trips between October, 2024 and March, 2025 on the KTH campus, the project involved:")
    st.markdown("- Analysis of sidewalk mobility patterns and assess delivery efficiency.")
    st.markdown("- Application of statistical and machine learning methods to evaluate the relation between sidewalk users’ patterns, contextual variables such as weather conditions, and pedestrian infrastructure features")
    st.markdown("## Team")

    col_robot,col_Xing, col_Michele,col_Kaj,col_Sulthan,col_Jonas = st.columns(6, border=False)
    with col_robot:
        st.image("data/pictures/Robot_photo.jpg",use_container_width=True)
        st.markdown("#### SVEA Robot")
        st.markdown("The SVEA robot used for sidewalk data collection and the mini network on KTH campus where the robot operates")
    with col_Xing:
        st.image("data/pictures/xingtong.jfif",use_container_width=True)
        st.markdown("#### Xing Tong")
        st.markdown("I am a Ph.D. student in the Division of Transport and Systems Analysis, engaging in the ISMIR project. My expertise lies in traffic analysis, GIS, and machine learning.")
        
    with col_Michele:
        st.image("data/pictures/micheles.jfif",use_container_width=True)
        st.markdown("#### Michele Simoni")
        st.markdown("Michele D. Simoni currently serves as an Assistant Professor in Transport Systems Analysis. Michele’s main research activity is currently focused on modeling and optimization of advanced transportation solutions.")
    
    with col_Kaj:
        st.image("data/pictures/kajarf.jfif",use_container_width=True)
        st.markdown("#### Kaj Munhoz Arfvidsson")
        st.markdown("I am a Ph.D. student in the Division of Transport and Systems Analysis, engaging in the ISMIR project. My expertise lies in traffic analysis, GIS, and machine learning.")
    
    with col_Sulthan:
        st.image("data/pictures/missing-profile-image.png",use_container_width=True)
        st.markdown("#### Sulthan Suresh Fazeela")
        st.markdown("I am a Research Engineer working primarily with sidewalk mobility and safe autonomous navigation for the small vehicles for autonomy (svea) platform at the Smart Mobility Lab.")

    with col_Jonas:
        st.image("data/pictures/jonas1.jfif",use_container_width=True)
        st.markdown("#### Jonas Mårtensson")
        st.markdown("Jonas Mårtensson is Professor of Automatic Control with applications in Transportation Systems at KTH Royal Institute of Technology in Stockholm, Sweden. He is the director of the Integrated Transport Research Lab (ITRL).")
        