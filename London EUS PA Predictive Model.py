import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta
import io
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, mean_squared_error

# Configuration Constants - Operating hours by day
OPERATIONAL_HOURS_WEEKDAY = [
    '07:00', '08:00', '09:00', '10:00', '11:00', '12:00', '13:00',
    '14:00', '15:00', '16:00', '17:00', '18:00', '19:00', '20:00',
    '21:00', '22:00', '23:00'
]

OPERATIONAL_HOURS_SUNDAY = [
    '08:00', '09:00', '10:00', '11:00', '12:00', '13:00',
    '14:00', '15:00', '16:00', '17:00', '18:00', '19:00', '20:00',
    '21:00', '22:00', '23:00'
]

DAYS_OF_WEEK = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']

# Updated hourly patterns (normalised for each day type)
HOURLY_PATTERNS = {
    'Weekday': {
        '07:00': 0.0156, '08:00': 0.0347, '09:00': 0.0448, '10:00': 0.0756,
        '11:00': 0.1109, '12:00': 0.1456, '13:00': 0.1456, '14:00': 0.1259,
        '15:00': 0.1055, '16:00': 0.0857, '17:00': 0.0732, '18:00': 0.0674,
        '19:00': 0.0606, '20:00': 0.0389, '21:00': 0.0269, '22:00': 0.0112,
        '23:00': 0.0079
    },
    'Sunday': {
        '08:00': 0.0347, '09:00': 0.0448, '10:00': 0.0756,
        '11:00': 0.1109, '12:00': 0.1456, '13:00': 0.1456, '14:00': 0.1259,
        '15:00': 0.1055, '16:00': 0.0857, '17:00': 0.0732, '18:00': 0.0674,
        '19:00': 0.0606, '20:00': 0.0389, '21:00': 0.0269, '22:00': 0.0112,
        '23:00': 0.0079
    }
}

# UK Bank Holidays dictionary
UK_BANK_HOLIDAYS = {
    2023: {
        'New Year\'s Day': '2023-01-02',
        'Easter': ('2023-04-07', '2023-04-10'),
        'Early May Bank Holiday': ('2023-04-29', '2023-05-01'),
        'Coronation Bank Holiday': ('2023-05-06', '2023-05-08'),
        'Spring Bank Holiday': ('2023-05-27', '2023-05-29'),
        'Summer Bank Holiday': ('2023-08-26', '2023-08-28'),
        'Christmas': ('2023-12-23', '2023-12-26'),
        'New Year\'s Day 2024': ('2023-12-30', '2024-01-01')
    },
    2024: {
        'Easter': ('2024-03-29', '2024-04-01'),
        'Early May Bank Holiday': ('2024-05-04', '2024-05-06'),
        'Spring Bank Holiday': ('2024-05-25', '2024-05-27'),
        'Summer Bank Holiday': ('2024-08-24', '2024-08-26'),
        'Christmas': ('2024-12-23', '2024-12-26'),
        'New Year\'s Day 2025': ('2024-12-28', '2025-01-01')
    },
    2025: {
        'Easter': ('2025-04-18', '2025-04-21'),
        'Early May Bank Holiday': ('2025-05-03', '2025-05-05'),
        'Spring Bank Holiday': ('2025-05-24', '2025-05-26'),
        'Summer Bank Holiday': ('2025-08-23', '2025-08-25'),
        'Christmas': ('2025-12-23', '2025-12-26'),
        'New Year\'s Day 2026': ('2025-12-27', '2026-01-01')
    },
    2026: {
        'Easter': ('2026-04-03', '2026-04-06'),
        'Early May Bank Holiday': ('2026-05-02', '2026-05-04'),
        'Spring Bank Holiday': ('2026-05-23', '2026-05-25'),
        'Summer Bank Holiday': ('2026-08-29', '2026-08-31'),
        'Christmas': ('2026-12-23', '2026-12-28'),
        'New Year\'s Day 2027': ('2026-12-26', '2027-01-01')
    }
}

DEFAULT_WEEKLY_PREDICTIONS = {
    'Sunday': 198, 'Monday': 302, 'Tuesday': 271, 'Wednesday': 271,
    'Thursday': 301, 'Friday': 289, 'Saturday': 280
}

DEFAULT_STAFF_EFFICIENCY = 4.26

# Initialise Session State
def initialise_session_state():
    """Initialise Streamlit session state with default values."""
    if 'roster_data' not in st.session_state:
        st.session_state.roster_data = None
    if 'trained_model' not in st.session_state:
        st.session_state.trained_model = None
    if 'weekly_predictions' not in st.session_state:
        st.session_state.weekly_predictions = DEFAULT_WEEKLY_PREDICTIONS.copy()
    if 'model_metrics' not in st.session_state:
        st.session_state.model_metrics = None

# Data Processing Functions
def process_datasets(uploaded_files):
    """Process uploaded CSV datasets for model training."""
    if not uploaded_files:
        return None
    
    dfs = []
    for file in uploaded_files:
        try:
            # Extract year from filename (e.g., "2023 Database.csv")
            year = int(file.name.split()[0])
            df = pd.read_csv(file)
            df['year'] = year
            dfs.append(df)
        except (ValueError, IndexError):
            st.error(f"Invalid filename format: {file.name}. Expected format: 'YYYY Database.csv'")
            continue
    
    if not dfs:
        return None
    
    # Sort by year and combine
    df_combined = pd.concat(sorted(dfs, key=lambda x: x['year'].iloc[0])).reset_index(drop=True)
    return df_combined

def train_demand_model(df_combined):
    """Train RandomForest model with Prophet-based dynamic growth factor."""
    if df_combined is None:
        return None, None, None
    
    try:
        # Filter for Euston station
        df_euston = df_combined[df_combined['station_code'] == "EUS"].copy()
        
        # Convert dates
        df_euston['scheduled_departure_date'] = pd.to_datetime(
            df_euston['scheduled_departure_date'], 
            dayfirst=True, 
            errors='coerce'
        )
        df_euston = df_euston.dropna(subset=['scheduled_departure_date'])
        
        # Aggregate bookings by date and year
        daily_bookings = df_euston.groupby(['scheduled_departure_date', 'year']).size().reset_index(name='total_bookings')
        
        # Find the newest year and check if it's complete
        newest_year = daily_bookings['year'].max()
        newest_year_data = daily_bookings[daily_bookings['year'] == newest_year]
        
        # Check if newest year is complete (has data through December)
        max_date_newest = newest_year_data['scheduled_departure_date'].max()
        is_complete_year = max_date_newest.month == 12 and max_date_newest.day >= 28
        
        st.info(f"📊 **Data Analysis:**\n"
                f"- Newest year: {newest_year}\n"
                f"- Last date: {max_date_newest.strftime('%Y-%m-%d')}\n"
                f"- Complete year: {'✅ Yes' if is_complete_year else '❌ No (partial)'}")
        
        # Calculate dynamic growth factor using Prophet if newest year is incomplete
        growth_factor = 1.0  # Default
        
        if not is_complete_year and len(daily_bookings['year'].unique()) >= 2:
            try:
                # Import Prophet
                from prophet import Prophet
                
                # Prepare Prophet data
                prophet_data = daily_bookings.groupby('scheduled_departure_date')['total_bookings'].sum().reset_index()
                prophet_data.columns = ['ds', 'y']
                
                # Apply empirical bounds (±1σ) to reduce noise for Prophet
                mean_bookings = prophet_data['y'].mean()
                std_bookings = prophet_data['y'].std()
                lower_bound = mean_bookings - std_bookings
                upper_bound = mean_bookings + std_bookings
                
                prophet_data = prophet_data[
                    (prophet_data['y'] >= lower_bound) & 
                    (prophet_data['y'] <= upper_bound)
                ]
                
                st.write(f"📈 **Prophet Training Data:** {len(prophet_data)} days (after ±1σ filtering)")
                
                # Split: train on all but newest incomplete year
                cutoff_date = f"{newest_year}-01-01"
                train_prophet = prophet_data[prophet_data['ds'] < cutoff_date]
                test_prophet = prophet_data[prophet_data['ds'] >= cutoff_date]
                
                if len(train_prophet) > 365:  # Need sufficient training data
                    # Train Prophet model
                    model_prophet = Prophet(
                        weekly_seasonality=True,
                        yearly_seasonality=True,
                        daily_seasonality=False
                    )
                    model_prophet.fit(train_prophet)
                    
                    # Create future dataframe for newest year
                    future_newest = model_prophet.make_future_dataframe(periods=365)
                    forecast = model_prophet.predict(future_newest)
                    
                    # Calculate growth factor from Prophet predictions
                    forecast['year'] = pd.to_datetime(forecast['ds']).dt.year
                    annual_avg = forecast.groupby('year')['yhat'].mean()
                    
                    prev_year = newest_year - 1
                    if prev_year in annual_avg.index and newest_year in annual_avg.index:
                        growth_factor = annual_avg[newest_year] / annual_avg[prev_year]
                        
                        # Evaluate Prophet on available newest year data
                        if len(test_prophet) > 0:
                            forecast_test = forecast[forecast['ds'].isin(test_prophet['ds'])]
                            if len(forecast_test) > 0:
                                prophet_mae = mean_absolute_error(test_prophet['y'], forecast_test['yhat'])
                                st.success(f"🔮 **Prophet Growth Factor:** {growth_factor:.3f} ({(growth_factor-1)*100:+.1f}%)\n"
                                          f"📊 **Prophet MAE:** {prophet_mae:.1f}")
                    
            except ImportError:
                st.warning("⚠️ Prophet not installed. Using fallback growth factor of 1.18")
                growth_factor = 1.18
            except Exception as e:
                st.warning(f"⚠️ Prophet calculation failed: {str(e)[:100]}... Using fallback growth factor of 1.18")
                growth_factor = 1.18
        else:
            growth_factor = 1.0 if is_complete_year else 1.18
            st.info(f"📈 **Growth Factor:** {growth_factor:.3f} ({'Complete year' if is_complete_year else 'Fallback'})")
        
        # Prepare training data with empirical bounds (±1σ)
        daily_bookings['day_of_week'] = daily_bookings['scheduled_departure_date'].dt.day_name()
        
        # Apply empirical bounds to reduce noise
        mean_bookings = daily_bookings['total_bookings'].mean()
        std_bookings = daily_bookings['total_bookings'].std()
        lower_bound = mean_bookings - std_bookings
        upper_bound = mean_bookings + std_bookings
        
        st.write(f"📊 **Training Data Empirical Bounds (μ ± 1σ):** {lower_bound:.1f} to {upper_bound:.1f}")
        
        daily_bookings_filtered = daily_bookings[
            (daily_bookings['total_bookings'] >= lower_bound) & 
            (daily_bookings['total_bookings'] <= upper_bound)
        ]
        
        # Train RandomForest on filtered data
        daily_bookings_encoded = pd.get_dummies(daily_bookings_filtered, columns=['day_of_week'], drop_first=True)
        
        features = ['year'] + [col for col in daily_bookings_encoded.columns if col.startswith('day_of_week_')]
        X = daily_bookings_encoded[features]
        y = daily_bookings_encoded['total_bookings']
        
        # Train model on all filtered data
        model = RandomForestRegressor(n_estimators=100, random_state=42)
        model.fit(X, y)
        
        # Calculate metrics using cross-validation approach
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
        model_test = RandomForestRegressor(n_estimators=100, random_state=42)
        model_test.fit(X_train, y_train)
        y_pred = model_test.predict(X_test)
        
        mae = mean_absolute_error(y_test, y_pred)
        rmse = np.sqrt(mean_squared_error(y_test, y_pred))
        mape = np.mean(np.abs((y_test - y_pred) / y_test)) * 100
        
        metrics = {'mae': mae, 'rmse': rmse, 'mape': mape, 'growth_factor': growth_factor}
        
        # Generate predictions for target year (newest year + 1 if incomplete, or newest year if complete)
        target_year = newest_year if is_complete_year else newest_year + 1
        
        predictions = {}
        for day in DAYS_OF_WEEK:
            # Create feature vector for target year
            feature_vector = pd.DataFrame({'year': [target_year]})
            
            # Add day of week dummy variables
            for col in features[1:]:  # Skip 'year'
                if col == f'day_of_week_{day}':
                    feature_vector[col] = 1
                else:
                    feature_vector[col] = 0
            
            # Ensure all columns are present
            for col in features:
                if col not in feature_vector.columns:
                    feature_vector[col] = 0
            
            # Reorder columns to match training data
            feature_vector = feature_vector[features]
            
            # Predict and apply growth factor
            prediction = model.predict(feature_vector)[0] * growth_factor
            predictions[day] = int(round(prediction))
        
        st.success(f"✅ **Model Trained Successfully!**\n"
                  f"📅 **Target Year:** {target_year}\n"
                  f"📊 **Training Samples:** {len(daily_bookings_filtered)} (after filtering)\n"
                  f"📈 **Applied Growth Factor:** {growth_factor:.3f}")
        
        return model, metrics, predictions
        
    except Exception as e:
        st.error(f"Error training model: {str(e)}")
        import traceback
        st.error(f"Full error: {traceback.format_exc()}")
        return None, None, None

def parse_time_format(time_str):
    """Parse different time formats and return HH:MM format."""
    if pd.isna(time_str) or time_str in ['OFF', 'SPARE', 'FD', '', 'RD', 'nan']:
        return None
    
    time_str = str(time_str).strip()
    
    # Handle different time formats
    if ':' in time_str:
        # Already in HH:MM format
        return time_str
    elif len(time_str) == 4 and time_str.isdigit():
        # Format like "0630" or "1430"
        return f"{time_str[:2]}:{time_str[2:]}"
    elif len(time_str) == 3 and time_str.isdigit():
        # Format like "630" (should be "06:30")
        return f"0{time_str[0]}:{time_str[1:]}"
    else:
        # Try to extract digits only
        digits_only = ''.join(filter(str.isdigit, time_str))
        if len(digits_only) == 4:
            return f"{digits_only[:2]}:{digits_only[2:]}"
        elif len(digits_only) == 3:
            return f"0{digits_only[0]}:{digits_only[1:]}"
    
    return None

def parse_roster_csv(uploaded_file):
    """Parse the uploaded CSV roster file with the correct format."""
    try:
        # Read the CSV file
        df = pd.read_csv(uploaded_file)
        
        # Debug: Show the structure of the uploaded file
        st.write("**Debug: File structure**")
        st.write(f"Columns: {list(df.columns)}")
        st.write("Sample data:")
        st.dataframe(df.head(10))
        
        roster_data = {}
        
        # Get day columns - they should be the actual day names
        day_columns = [col for col in df.columns if col in DAYS_OF_WEEK]
        
        if not day_columns:
            st.error("Could not find day columns. Please check your CSV format.")
            st.write(f"Expected columns: {DAYS_OF_WEEK}")
            st.write(f"Found columns: {list(df.columns)}")
            return None
        
        # Initialise roster data for each day
        for day in DAYS_OF_WEEK:
            roster_data[day] = []
        
        # Process the data - your format has staff names in first column and alternating time/shift rows
        i = 0
        while i < len(df):
            # Get the staff member name from the first column
            staff_name = str(df.iloc[i, 0]).strip() if not pd.isna(df.iloc[i, 0]) else ""
            
            # Skip empty rows or header rows
            if not staff_name or staff_name == 'nan' or ',' in staff_name:
                i += 1
                continue
            
            # Get the time row (current row)
            time_row = df.iloc[i]
            
            # Get the shift code row (next row if it exists)
            shift_row = None
            if i + 1 < len(df):
                next_row_name = str(df.iloc[i + 1, 0]).strip() if not pd.isna(df.iloc[i + 1, 0]) else ""
                # If next row doesn't have a staff name, it's probably the shift codes
                if not next_row_name or next_row_name == 'nan':
                    shift_row = df.iloc[i + 1]
                    i += 2  # Skip both rows
                else:
                    i += 1  # Only skip current row
            else:
                i += 1
            
            # Process each day column
            for day in day_columns:
                if day not in df.columns:
                    continue
                
                # Get time info and shift code
                time_info = str(time_row[day]).strip() if not pd.isna(time_row[day]) else ""
                shift_code = ""
                if shift_row is not None:
                    shift_code = str(shift_row[day]).strip() if not pd.isna(shift_row[day]) else ""
                
                # Skip if OFF, SPARE, RD, or empty
                if time_info in ['OFF', 'SPARE', 'RD', '', 'nan', 'Vacancy']:
                    continue
                
                # Parse time range (e.g., "1500-2300" or "0630-1430")
                if '-' in time_info:
                    try:
                        start_time_str, end_time_str = time_info.split('-')
                        start_time = parse_time_format(start_time_str)
                        end_time = parse_time_format(end_time_str)
                        
                        if start_time and end_time:
                            roster_data[day].append((start_time, end_time))
                            st.write(f"Added shift for {staff_name} on {day}: {start_time} - {end_time}")
                            
                    except ValueError as e:
                        st.write(f"Could not parse time range '{time_info}' for {staff_name} on {day}: {e}")
                        continue
                
                # Handle standalone shift codes (fallback)
                elif shift_code in ['8', '10'] and time_info not in ['OFF', 'SPARE', 'RD', '', 'nan']:
                    if shift_code == '8':
                        # Default 8-hour shift: 06:30-14:30
                        roster_data[day].append(('06:30', '14:30'))
                        st.write(f"Added default 8h shift for {staff_name} on {day}: 06:30 - 14:30")
                    elif shift_code == '10':
                        # Default 10-hour shift: 06:30-16:30
                        roster_data[day].append(('06:30', '16:30'))
                        st.write(f"Added default 10h shift for {staff_name} on {day}: 06:30 - 16:30")
        
        # Show parsed results
        st.write("**Parsed roster summary:**")
        total_shifts = 0
        for day, shifts in roster_data.items():
            if shifts:  # Only show days with shifts
                st.write(f"**{day}:** {len(shifts)} shifts")
                total_shifts += len(shifts)
                for idx, (start, end) in enumerate(shifts[:5]):  # Show first 5 shifts
                    st.write(f"  • {start} - {end}")
                if len(shifts) > 5:
                    st.write(f"  ... and {len(shifts) - 5} more")
        
        if total_shifts > 0:
            st.success(f"✅ Successfully parsed {total_shifts} total shifts across all days")
        else:
            st.warning("⚠️ No shifts were parsed. Please check your CSV format.")
            st.write("**Expected format:**")
            st.write("- Staff names in first column")
            st.write("- Day columns: Sunday, Monday, Tuesday, etc.")
            st.write("- Time ranges like '0630-1430', '1500-2300'")
            st.write("- Non-working entries: 'OFF', 'SPARE', 'RD'")
        
        return roster_data
        
    except Exception as e:
        st.error(f"Error parsing roster file: {str(e)}")
        st.write("**Error details:**")
        st.write(str(e))
        st.write("**Troubleshooting tips:**")
        st.write("1. Make sure your CSV has day columns (Sunday, Monday, etc.)")
        st.write("2. Time format should be: '0630-1430' or '1500-2300'")
        st.write("3. Non-working entries: 'OFF', 'SPARE', 'RD'")
        st.write("4. Staff names should be in the first column")
        return None

def analyse_bank_holiday_patterns(df_combined):
    """Analyse bank holiday patterns and generate predictions."""
    if df_combined is None:
        return None
    
    try:
        # Filter for Euston station
        df_euston = df_combined[df_combined['station_code'] == "EUS"].copy()
        
        # Convert dates
        df_euston['scheduled_departure_date'] = pd.to_datetime(
            df_euston['scheduled_departure_date'], 
            dayfirst=True, 
            errors='coerce'
        )
        df_euston = df_euston.dropna(subset=['scheduled_departure_date'])
        
        # Aggregate bookings by date
        daily_bookings = df_euston.groupby('scheduled_departure_date').size().reset_index(name='bookings')
        daily_bookings['day_of_week'] = daily_bookings['scheduled_departure_date'].dt.day_name()
        
        # Calculate normal day averages for comparison
        normal_averages = {}
        for day in DAYS_OF_WEEK:
            day_data = daily_bookings[daily_bookings['day_of_week'] == day]['bookings']
            if len(day_data) > 0:
                # Apply ±1σ filter
                mean_val = day_data.mean()
                std_val = day_data.std()
                filtered_data = day_data[(day_data >= mean_val - std_val) & (day_data <= mean_val + std_val)]
                normal_averages[day] = filtered_data.mean() if len(filtered_data) > 0 else mean_val
        
        # Analyse each bank holiday
        bank_holiday_analysis = []
        
        for year, holidays in UK_BANK_HOLIDAYS.items():
            if year > daily_bookings['scheduled_departure_date'].dt.year.max():
                continue
                
            for holiday_name, dates in holidays.items():
                if isinstance(dates, tuple):
                    start_date, end_date = dates
                    start_date = pd.to_datetime(start_date)
                    end_date = pd.to_datetime(end_date)
                else:
                    start_date = end_date = pd.to_datetime(dates)
                
                # Get pre and post days
                pre_date = start_date - timedelta(days=1)
                post_date = end_date + timedelta(days=1)
                
                # Get data for each period
                analysis = {
                    'holiday_name': holiday_name,
                    'year': year,
                    'start_date': start_date,
                    'end_date': end_date,
                    'pre_date': pre_date,
                    'post_date': post_date,
                    'holiday_bookings': {},
                    'pre_booking': None,
                    'post_booking': None
                }
                
                # Pre-day analysis
                pre_data = daily_bookings[daily_bookings['scheduled_departure_date'] == pre_date]
                if len(pre_data) > 0:
                    pre_booking = pre_data['bookings'].iloc[0]
                    pre_day = pre_data['day_of_week'].iloc[0]
                    normal_pre = normal_averages.get(pre_day, 0)
                    pre_pct = ((pre_booking - normal_pre) / normal_pre * 100) if normal_pre > 0 else 0
                    analysis['pre_booking'] = {
                        'date': pre_date,
                        'day': pre_day,
                        'bookings': pre_booking,
                        'percentage_diff': pre_pct
                    }
                
                # Holiday period analysis
                current_date = start_date
                while current_date <= end_date:
                    holiday_data = daily_bookings[daily_bookings['scheduled_departure_date'] == current_date]
                    if len(holiday_data) > 0:
                        analysis['holiday_bookings'][current_date] = {
                            'bookings': holiday_data['bookings'].iloc[0],
                            'day': holiday_data['day_of_week'].iloc[0]
                        }
                    current_date += timedelta(days=1)
                
                # Post-day analysis
                post_data = daily_bookings[daily_bookings['scheduled_departure_date'] == post_date]
                if len(post_data) > 0:
                    post_booking = post_data['bookings'].iloc[0]
                    post_day = post_data['day_of_week'].iloc[0]
                    normal_post = normal_averages.get(post_day, 0)
                    post_pct = ((post_booking - normal_post) / normal_post * 100) if normal_post > 0 else 0
                    analysis['post_booking'] = {
                        'date': post_date,
                        'day': post_day,
                        'bookings': post_booking,
                        'percentage_diff': post_pct
                    }
                
                if analysis['holiday_bookings']:  # Only add if we have holiday data
                    bank_holiday_analysis.append(analysis)
        
        return bank_holiday_analysis, normal_averages
        
    except Exception as e:
        st.error(f"Error analysing bank holiday patterns: {str(e)}")
        return None, None

def predict_bank_holiday_demand(df_combined, target_date):
    """Predict demand for a specific bank holiday using Prophet-based growth factor."""
    if df_combined is None:
        return None
    
    try:
        # Get bank holiday analysis
        bank_holiday_analysis, normal_averages = analyse_bank_holiday_patterns(df_combined)
        if not bank_holiday_analysis:
            return None
        
        # Find which bank holiday the target_date falls into
        target_pd = pd.to_datetime(target_date)
        matching_holiday = None
        
        for year, holidays in UK_BANK_HOLIDAYS.items():
            for holiday_name, dates in holidays.items():
                if isinstance(dates, tuple):
                    start_date, end_date = dates
                    start_date = pd.to_datetime(start_date)
                    end_date = pd.to_datetime(end_date)
                else:
                    start_date = end_date = pd.to_datetime(dates)
                
                if start_date <= target_pd <= end_date:
                    matching_holiday = {
                        'name': holiday_name,
                        'year': year,
                        'start': start_date,
                        'end': end_date
                    }
                    break
        
        if not matching_holiday:
            return None
        
        # Find historical patterns for this holiday type
        holiday_patterns = []
        for analysis in bank_holiday_analysis:
            if matching_holiday['name'].replace(f" {matching_holiday['year']}", "") in analysis['holiday_name']:
                holiday_patterns.append(analysis)
        
        if not holiday_patterns:
            return None
        
        # Calculate Prophet-based growth factor
        growth_factor = 1.0
        try:
            from prophet import Prophet
            
            # Prepare data for Prophet
            df_euston = df_combined[df_combined['station_code'] == "EUS"].copy()
            df_euston['scheduled_departure_date'] = pd.to_datetime(
                df_euston['scheduled_departure_date'], dayfirst=True, errors='coerce'
            )
            df_euston = df_euston.dropna(subset=['scheduled_departure_date'])
            
            daily_bookings = df_euston.groupby('scheduled_departure_date').size().reset_index()
            daily_bookings.columns = ['ds', 'y']
            
            # Apply empirical bounds
            mean_bookings = daily_bookings['y'].mean()
            std_bookings = daily_bookings['y'].std()
            daily_bookings = daily_bookings[
                (daily_bookings['y'] >= mean_bookings - std_bookings) & 
                (daily_bookings['y'] <= mean_bookings + std_bookings)
            ]
            
            # Train Prophet
            newest_year = daily_bookings['ds'].dt.year.max()
            train_data = daily_bookings[daily_bookings['ds'].dt.year < newest_year]
            
            if len(train_data) > 365:
                model_prophet = Prophet(weekly_seasonality=True, yearly_seasonality=True)
                model_prophet.fit(train_data)
                
                # Calculate growth factor
                forecast = model_prophet.predict(daily_bookings[['ds']])
                forecast['year'] = forecast['ds'].dt.year
                annual_avg = forecast.groupby('year')['yhat'].mean()
                
                if newest_year in annual_avg.index and (newest_year - 1) in annual_avg.index:
                    growth_factor = annual_avg[newest_year] / annual_avg[newest_year - 1]
        
        except:
            growth_factor = 1.18  # Fallback
        
        # Calculate predictions based on historical patterns
        predictions = {}
        for pattern in holiday_patterns:
            for date, booking_data in pattern['holiday_bookings'].items():
                if date.day == target_pd.day and date.month == target_pd.month:
                    base_demand = booking_data['bookings']
                    predicted_demand = int(round(base_demand * growth_factor))
                    predictions[date] = {
                        'historical_demand': base_demand,
                        'predicted_demand': predicted_demand,
                        'growth_factor': growth_factor,
                        'year': pattern['year']
                    }
        
        return {
            'holiday': matching_holiday,
            'predictions': predictions,
            'historical_patterns': holiday_patterns,
            'growth_factor': growth_factor
        }
        
    except Exception as e:
        st.error(f"Error predicting bank holiday demand: {str(e)}")
        return None

def time_to_minutes(time_str):
    """Convert HH:MM time string to minutes since midnight."""
    if not time_str or ':' not in time_str:
        return 0
    
    try:
        hours, minutes = map(int, time_str.split(':'))
        return hours * 60 + minutes
    except:
        return 0

def get_operational_hours(day_of_week):
    """Get operational hours based on day of week."""
    if day_of_week == 'Sunday':
        return OPERATIONAL_HOURS_SUNDAY
    else:
        return OPERATIONAL_HOURS_WEEKDAY

def calculate_hourly_coverage(roster_data, selected_day):
    """Calculate hourly staff coverage for a given day with improved time handling."""
    if not roster_data or selected_day not in roster_data:
        operational_hours = get_operational_hours(selected_day)
        return {hour: 0 for hour in operational_hours}
    
    operational_hours = get_operational_hours(selected_day)
    coverage = {hour: 0 for hour in operational_hours}
    
    for start_time, end_time in roster_data[selected_day]:
        # Convert times to minutes for accurate comparison
        start_minutes = time_to_minutes(start_time)
        end_minutes = time_to_minutes(end_time)
        
        # Count staff for each operational hour
        for hour_str in operational_hours:
            hour_minutes = time_to_minutes(hour_str)
            
            # Check if this hour falls within the shift
            # A shift covers an hour if the hour is >= start and < end
            if start_minutes <= hour_minutes < end_minutes:
                coverage[hour_str] += 1
    
    return coverage

def calculate_hourly_demand(total_customers, day_of_week, hourly_pattern=None):
    """Calculate hourly customer demand based on day of week."""
    operational_hours = get_operational_hours(day_of_week)
    
    if hourly_pattern is None:
        if day_of_week == 'Sunday':
            hourly_pattern = HOURLY_PATTERNS['Sunday']
        else:
            hourly_pattern = HOURLY_PATTERNS['Weekday']
    
    return {
        hour: int(round(total_customers * hourly_pattern.get(hour, 0)))
        for hour in operational_hours
    }

def generate_recommendations(hourly_demand, hourly_coverage, efficiency=DEFAULT_STAFF_EFFICIENCY):
    """Generate staffing recommendations based on demand vs coverage."""
    recommendations = {}
    
    for hour in hourly_demand.keys():
        demand = hourly_demand.get(hour, 0)
        coverage = hourly_coverage.get(hour, 0)
        
        # Calculate required staff based on efficiency
        required_staff = np.ceil(demand / efficiency) if demand > 0 else 1
        
        if coverage < required_staff:
            deficit = int(required_staff - coverage)
            recommendations[hour] = f"⚠️ Add {deficit} staff (Current: {coverage}, Required: {int(required_staff)})"
        elif coverage > required_staff * 1.2:  # 20% buffer
            excess = int(coverage - required_staff)
            recommendations[hour] = f"ℹ️ Excess {excess} staff (Current: {coverage}, Required: {int(required_staff)})"
        else:
            recommendations[hour] = f"✅ Adequate (Current: {coverage}, Required: {int(required_staff)})"
    
    return recommendations

# Streamlit App
def main():
    st.set_page_config(
        page_title="London Euston Rostering Reference Tool",
        page_icon="🚂",
        layout="wide"
    )
    
    initialise_session_state()
    
    st.title("🚂 London Euston Rostering Reference Tool")
    st.markdown("An intelligent tool to analyse customer demand against fixed roster schedules")
    
    # Sidebar for data uploads and model training
    with st.sidebar:
        st.header("📊 Data Management")
        
        # Roster file upload
        st.subheader("Fixed Roster Schedule")
        st.info("📝 **CSV File Format Requirements:**\n"
                "**Your Format:**\n"
                "- Day columns: Sunday, Monday, Tuesday, etc.\n"
                "- Staff names in first column\n"
                "- Time ranges (e.g., '0630-1430', '1500-2300')\n"
                "- Non-working: 'OFF', 'SPARE', 'RD'\n"
                "- Shift codes in alternating rows (optional)")
        
        roster_file = st.file_uploader(
            "Upload 2025 Roster CSV File",
            type=['csv'],
            help="Upload the CSV file containing the fixed weekly roster schedule"
        )
        
        if roster_file:
            roster_data = parse_roster_csv(roster_file)
            if roster_data:
                st.session_state.roster_data = roster_data
                st.success("✅ Roster file loaded successfully!")
                
                # Display roster summary
                with st.expander("View Roster Summary"):
                    for day, shifts in roster_data.items():
                        if shifts:  # Only show days with shifts
                            st.write(f"**{day}:** {len(shifts)} shifts")
                            for start, end in shifts:
                                st.write(f"  • {start} - {end}")
        
        st.divider()
        
        # Historical data upload for model training
        st.subheader("Historical Data Training")
        uploaded_files = st.file_uploader(
            "Upload Historical CSV Files",
            accept_multiple_files=True,
            type="csv",
            help="Upload CSV files named like '2023 Database.csv', '2024 Database.csv'"
        )
        
        if uploaded_files:
            if st.button("🔄 Train Prediction Model"):
                with st.spinner("Training model..."):
                    df_combined = process_datasets(uploaded_files)
                    if df_combined is not None:
                        model, metrics, predictions = train_demand_model(df_combined)
                        if model and metrics and predictions:
                            st.session_state.trained_model = model
                            st.session_state.model_metrics = metrics
                            st.session_state.weekly_predictions = predictions
                            st.success("✅ Model trained successfully!")
                            
                            # Display metrics
                            col1, col2, col3, col4 = st.columns(4)
                            with col1:
                                st.metric("MAE", f"{metrics['mae']:.1f}")
                            with col2:
                                st.metric("MAPE", f"{metrics['mape']:.1f}%")
                            with col3:
                                st.metric("RMSE", f"{metrics['rmse']:.1f}")
                            with col4:
                                st.metric("Growth Factor", f"{metrics['growth_factor']:.3f}")
                        else:
                            st.error("❌ Failed to train model. Please check your data format.")
        
        # Display current predictions
        if st.session_state.weekly_predictions:
            st.subheader("📈 Weekly Predictions")
            for day, prediction in st.session_state.weekly_predictions.items():
                st.write(f"**{day}:** {prediction} customers")
        
        st.divider()
        
        # Bank Holiday Analysis Section
        st.subheader("🏖️ Bank Holiday Analysis")
        st.info("📊 **Bank Holiday Features:**\n"
                "- Analyses historical UK bank holiday patterns\n"
                "- Compares pre/during/post holiday demands\n"
                "- Uses Prophet growth factor for predictions\n"
                "- Shows percentage differences vs normal days")
        
        bank_holiday_files = st.file_uploader(
            "Upload Historical CSV Files for Bank Holiday Analysis",
            accept_multiple_files=True,
            type="csv",
            key="bank_holiday_files",
            help="Upload the same historical CSV files for bank holiday pattern analysis"
        )
        
        if bank_holiday_files:
            if st.button("🔍 Analyse Bank Holiday Patterns"):
                with st.spinner("Analysing bank holiday patterns..."):
                    df_combined_bh = process_datasets(bank_holiday_files)
                    if df_combined_bh is not None:
                        bank_holiday_analysis, normal_averages = analyse_bank_holiday_patterns(df_combined_bh)
                        if bank_holiday_analysis:
                            st.session_state.bank_holiday_analysis = bank_holiday_analysis
                            st.session_state.bank_holiday_normals = normal_averages
                            st.session_state.bank_holiday_data = df_combined_bh
                            st.success(f"✅ Analysed {len(bank_holiday_analysis)} bank holiday periods!")
                            
                            # Show summary
                            st.write("**Bank Holiday Summary:**")
                            for analysis in bank_holiday_analysis[-5:]:  # Show last 5
                                st.write(f"• {analysis['holiday_name']}: {analysis['start_date'].strftime('%d/%m/%Y')} - {analysis['end_date'].strftime('%d/%m/%Y')}")
                        else:
                            st.error("❌ No bank holiday data found in the provided files")
        
        # Bank holiday prediction section
        if hasattr(st.session_state, 'bank_holiday_analysis'):
            st.subheader("🎯 Bank Holiday Prediction")
            
            # Date picker for bank holiday
            bh_date = st.date_input(
                "Select Bank Holiday Date",
                value=datetime.now().date(),
                help="Choose a bank holiday date for analysis"
            )
            
            if st.button("📊 Generate Bank Holiday Report"):
                prediction_result = predict_bank_holiday_demand(st.session_state.bank_holiday_data, bh_date)
                if prediction_result:
                    st.session_state.current_bh_prediction = prediction_result
                    st.success(f"✅ Generated prediction for {prediction_result['holiday']['name']}")
                else:
                    st.warning("⚠️ Selected date is not a recognised UK bank holiday")
    
    # Main content area
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.header("📅 Date Selection")
        selected_date = st.date_input(
            "Select Date for Analysis",
            value=datetime.now().date(),
            help="Choose the date you want to analyse"
        )
        
        day_of_week = selected_date.strftime('%A')
        st.info(f"Selected day: **{day_of_week}**")
    
    with col2:
        st.header("📊 Day Type Configuration")
        day_type = st.radio(
            "Select day type",
            ["Normal day", "Bank holiday", "Other"],
            help="Choose the type of day for accurate predictions"
        )
    
    # Determine customer count based on day type
    if day_type == "Normal day":
        predicted_customers = st.session_state.weekly_predictions.get(day_of_week, 0)
        st.success(f"🎯 Predicted customers: **{predicted_customers}** (±20% MAE)")
        total_customers = predicted_customers
        
    elif day_type == "Bank holiday":
        st.info("🚧 Bank holiday predictions will be available in future updates")
        total_customers = st.number_input(
            "Enter expected customers for bank holiday",
            min_value=0,
            value=200,
            help="Manually enter expected customer count"
        )
        
    else:  # Other
        total_customers = st.number_input(
            "Enter expected customer count",
            min_value=0,
            value=300,
            help="Manually enter expected customer count"
        )
    
    # Analysis section
    if total_customers > 0:
        st.header("📊 Demand vs Roster Analysis")
        
        # Calculate hourly demand and coverage
        hourly_demand = calculate_hourly_demand(total_customers, day_of_week)
        
        if st.session_state.roster_data:
            hourly_coverage = calculate_hourly_coverage(st.session_state.roster_data, day_of_week)
            recommendations = generate_recommendations(hourly_demand, hourly_coverage)
            
            # Create visualisation
            fig = go.Figure()
            
            # Customer demand bars
            operational_hours = get_operational_hours(day_of_week)
            fig.add_trace(go.Bar(
                x=operational_hours,
                y=list(hourly_demand.values()),
                name="Customer Demand",
                marker_color='lightblue',
                opacity=0.7,
                yaxis='y'
            ))
            
            # Staff coverage line
            fig.add_trace(go.Scatter(
                x=operational_hours,
                y=list(hourly_coverage.values()),
                name="Rostered Staff",
                mode='lines+markers',
                line=dict(color='green', width=3),
                marker=dict(size=8),
                yaxis='y2'
            ))
            
            # Highlight problem hours
            understaffed_hours = []
            overstaffed_hours = []
            
            for hour in operational_hours:
                demand = hourly_demand[hour]
                coverage = hourly_coverage[hour]
                required = np.ceil(demand / DEFAULT_STAFF_EFFICIENCY)
                
                if coverage < required:
                    understaffed_hours.append(hour)
                elif coverage > required * 1.2:
                    overstaffed_hours.append(hour)
            
            if understaffed_hours:
                fig.add_trace(go.Scatter(
                    x=understaffed_hours,
                    y=[hourly_coverage[h] for h in understaffed_hours],
                    name='Understaffed Hours',
                    mode='markers',
                    marker=dict(color='red', size=12, symbol='x'),
                    yaxis='y2'
                ))
            
            fig.update_layout(
                title=f"Customer Demand vs Roster Coverage - {day_of_week}, {selected_date}",
                xaxis_title="Hour of Day",
                yaxis=dict(title="Customer Count", side='left'),
                yaxis2=dict(title="Staff Count", side='right', overlaying='y'),
                xaxis_tickangle=45,
                showlegend=True,
                height=500
            )
            
            st.plotly_chart(fig, use_container_width=True)
            
            # Recommendations table
            st.subheader("📋 Hourly Recommendations")
            
            rec_data = []
            for hour in operational_hours:
                rec_data.append({
                    'Hour': hour,
                    'Customer Demand': hourly_demand[hour],
                    'Rostered Staff': hourly_coverage[hour],
                    'Recommendation': recommendations[hour]
                })
            
            rec_df = pd.DataFrame(rec_data)
            st.dataframe(rec_df, use_container_width=True, hide_index=True)
            
            # Summary metrics
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric("Total Customers", f"{total_customers:,}")
            
            with col2:
                total_staff_hours = sum(hourly_coverage.values())
                st.metric("Total Staff Hours", f"{total_staff_hours}")
            
            with col3:
                understaffed_count = len(understaffed_hours)
                st.metric("Understaffed Hours", f"{understaffed_count}", 
                         delta=f"-{understaffed_count}" if understaffed_count > 0 else None)
            
            with col4:
                efficiency_ratio = (total_customers / (total_staff_hours * DEFAULT_STAFF_EFFICIENCY)) * 100 if total_staff_hours > 0 else 0
                st.metric("Efficiency Ratio", f"{efficiency_ratio:.1f}%")
            
            # Download option
            csv_buffer = io.StringIO()
            rec_df.to_csv(csv_buffer, index=False)
            st.download_button(
                label="📥 Download Analysis Report",
                data=csv_buffer.getvalue(),
                file_name=f"roster_analysis_{selected_date}_{day_of_week}.csv",
                mime="text/csv"
            )
            
        else:
            st.warning("⚠️ Please upload the roster CSV file to see coverage analysis")
            
            # Show demand distribution only
            fig = go.Figure()
            operational_hours = get_operational_hours(day_of_week)
            fig.add_trace(go.Bar(
                x=operational_hours,
                y=list(hourly_demand.values()),
                name="Customer Demand",
                marker_color='lightblue'
            ))
            
            fig.update_layout(
                title=f"Customer Demand Distribution - {day_of_week}, {selected_date}",
                xaxis_title="Hour of Day",
                yaxis_title="Customer Count",
                xaxis_tickangle=45,
                height=400
            )
            
            st.plotly_chart(fig, use_container_width=True)
    
    # Footer
    st.markdown("---")
    st.markdown("""
    ### 📝 Model Notes
    - **Adaptive Training**: Automatically detects incomplete years and calculates dynamic growth factors
    - **Prophet Integration**: Uses Prophet model for growth factor calculation when newest year is incomplete
    - **Empirical Filtering**: Applies ±1σ bounds to training data to reduce noise and outliers
    - **Smart Predictions**: Targets next year for incomplete data, current year for complete datasets
    - **Hourly Distribution**: Uses standard patterns optimised for London Euston station (starts from 06:30)
    - **Staff Efficiency**: Default rate of 4.26 customers per staff hour
    - **Recommendations**: Based on demand vs coverage analysis with 20% buffer for adequate staffing
    """)

if __name__ == "__main__":
    main()