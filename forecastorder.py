import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import calendar

st.title('RL Qty Calculator')

# Load Vendor Details from GitHub
vendor_details = st.file_uploader('Upload Vendor Details (CSV)', type='csv')
if vendor_details is not None:
    vendor_df = pd.read_csv(vendor_details, on_bad_lines="skip")
    vendor_df.columns = vendor_df.columns.str.strip()

# Translate day names to dates
def get_next_weekday(day_name):
    today = datetime(2025, 4, 7)()
    days_ahead = (list(calendar.day_name).index(day_name) - today.weekday() + 7) % 7
    return today + timedelta(days=days_ahead + 7)

# Calculate order, inbound, and coverage days based on vendor schedule
def calculate_dates(row):
    order_date = get_next_weekday(row['Ideal RL submission'])
    inbound_date = order_date + timedelta(days=row['JI'])
    next_inbound_date = inbound_date + timedelta(days=row['JI'])
    coverage_days = next_inbound_date - order_date
    return pd.Series([order_date, inbound_date, next_inbound_date, coverage_days])

vendor_df[['order_date', 'inbound_date', 'next_inbound_date', 'coverage_days']] = vendor_df.apply(calculate_dates, axis=1)

# File uploads
sales_forecast = st.file_uploader('Upload Sales Forecast (CSV)', type='csv')
safety_stock = st.file_uploader('Upload Safety Stock Data (CSV)', type='csv')
reference_soh = st.file_uploader('Upload Reference SOH Data (CSV)', type='csv')

if st.button('Calculate RL Qty'):
    try:
        # Load data from files
        sales_df = pd.read_csv(sales_forecast)
        safety_df = pd.read_csv(safety_stock)
        soh_df = pd.read_csv(reference_soh)

        # Merge data
        merged_df = soh_df.merge(sales_df, on='product_id', how='left')
        merged_df = merged_df.merge(safety_df, on='product_id', how='left')
        merged_df = merged_df.merge(vendor_df, on='product_id', how='left')

        # Calculate current stock as reference SOH + OSPO + OSPR + OSRL
        merged_df['current_stock'] = merged_df['stock_wh'] + merged_df['ospo_qty'] + merged_df['ospr_qty'] + merged_df['osrl_qty']

        # Loop through 4 cycles based on forecast sales dates
        results = []
        for cycle in range(4):
            cycle_date = datetime.now() + timedelta(days=cycle * 7)
            merged_df['Next SOH WH'] = merged_df['current_stock'] + merged_df['ospo_qty'] - merged_df['avg_sales'] * (merged_df['coverage_days'] - merged_df['order_date']).dt.days
            merged_df['Max Stock WH'] = merged_df['avg_sales'] * (merged_df['coverage_days'].dt.days + merged_df['doi_policy'])
            merged_df['RL Qty'] = merged_df['Max Stock WH'] - merged_df['Next SOH WH'] - merged_df['ospo_qty'] - merged_df['ospr_qty'] - merged_df['osrl_qty']
            results.append(merged_df[['product_id', 'Next SOH WH', 'Max Stock WH', 'RL Qty']].copy())
            merged_df['ospo_qty'] = merged_df['RL Qty']  # Set RL Qty as OSPO for next cycle
            merged_df['current_stock'] = merged_df['Next SOH WH']

        # Combine results from all cycles
        final_results = pd.concat(results, keys=range(1, 5), names=['Cycle'])

        # Display results
        st.write('RL Qty Calculation Results:')
        st.dataframe(final_results)
        st.download_button(label='Download Results as CSV', data=final_results.to_csv(index=True), file_name='rl_qty_results.csv')
    except Exception as e:
        st.error(f'Error during calculation: {e}')
