# Data sources — TrendCast (forecasting dashboard)

- Primary: **WFP VAM food prices** via the HDX (Humanitarian Data Exchange) API — Pakistan wheat/flour retail series. Save the downloaded CSVs in this folder with the download date in the filename.
- Secondary: **Pakistan Bureau of Statistics SPI** (Sensitive Price Indicator) weekly releases.
- Fallback: a public energy-demand series (e.g. a well-known public dataset) if food-price access fails — see IMPLEMENTATION_PLAN.md risk table.
- All downloads must be snapshotted (never overwritten): `data/processed/` holds versioned parquet files built from these raw files, with a manifest recording source + date.
