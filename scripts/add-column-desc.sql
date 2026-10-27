-- =============================================================================
-- BigQuery Table & Column Descriptions for Dataset:
--   `qwiklabs-gcp-04-f5825262a0a0.a4i_health`
--
-- Grounded in:
--   - README.md, data/README.md, scripts/README.md, agent/README.md
--   - scripts/load.sh
--   - notebooks/c5_01_load_explore.ipynb
--   - Live BigQuery schemas in `qwiklabs-gcp-04-f5825262a0a0.a4i_health`
-- =============================================================================

-- =============================================================================
-- 1. TABLE: burden_tracts
-- =============================================================================
ALTER TABLE `qwiklabs-gcp-04-f5825262a0a0.a4i_health.burden_tracts`
SET OPTIONS (
  description = 'Census-tract chronic disease burden, preventive care, disability, and social vulnerability indicators (1 row per 2020 census tract). Combines CDC PLACES 2025 model-based small-area estimates (not direct clinic counts; tracts with tiny population are suppressed) with CDC/ATSDR Social Vulnerability Index (SVI 2022, with -999 sentinels converted to NULL). SVI Theme 3 (Racial & Ethnic Minority Status) and overall RPL_THEMES are intentionally excluded from siting inputs and reserved for post-hoc equity auditing.'
);

ALTER TABLE `qwiklabs-gcp-04-f5825262a0a0.a4i_health.burden_tracts`
  ALTER COLUMN geo_id SET OPTIONS (
    description = '11-character 2020 Census tract FIPS code (zero-padded STRING: 2-digit state + 3-digit county + 6-digit tract; e.g., 13121007603). Primary join key across tract-level tables; preserve as STRING so leading zeros for states with FIPS < 10 are not stripped.'
  ),
  ALTER COLUMN total_pop SET OPTIONS (
    description = 'Total resident population of the census tract reported by CDC PLACES (source column: totalpopulation). Tracts with very small or zero population are suppressed by PLACES.'
  ),
  ALTER COLUMN pct_uninsured SET OPTIONS (
    description = 'Modeled crude prevalence (%) of lack of health insurance among working-age adults aged 18-64 from CDC PLACES (source: access2_crudeprev). Small-area MRP estimate, not a direct count. Reads systematically higher than pct_uninsured_all_ages in older tracts because Medicare covers nearly all adults 65+.'
  ),
  ALTER COLUMN pct_asthma SET OPTIONS (
    description = 'Modeled crude prevalence (%) of current asthma among adults aged >=18 from CDC PLACES (source: casthma_crudeprev). Higher values indicate greater respiratory burden.'
  ),
  ALTER COLUMN pct_copd SET OPTIONS (
    description = 'Modeled crude prevalence (%) of chronic obstructive pulmonary disease (COPD), emphysema, or chronic bronchitis among adults aged >=18 from CDC PLACES (source: copd_crudeprev). Higher values indicate greater chronic respiratory burden.'
  ),
  ALTER COLUMN pct_diabetes SET OPTIONS (
    description = 'Modeled crude prevalence (%) of diagnosed diabetes among adults aged >=18 from CDC PLACES (source: diabetes_crudeprev). Higher values indicate greater cardiometabolic burden.'
  ),
  ALTER COLUMN pct_high_bp SET OPTIONS (
    description = 'Modeled crude prevalence (%) of high blood pressure (hypertension) among adults aged >=18 from CDC PLACES (source: bphigh_crudeprev). Higher values indicate greater cardiovascular burden.'
  ),
  ALTER COLUMN pct_checkup SET OPTIONS (
    description = 'Modeled crude prevalence (%) of adults aged >=18 who visited a doctor for a routine checkup within the past year from CDC PLACES (source: checkup_crudeprev). DIRECTIONALITY WARNING: LOW values indicate higher unmet preventive care need, whereas HIGH values indicate worse burden on all other PLACES disease columns. Invert as (100 - pct_checkup) before combining into composite need scores.'
  ),
  ALTER COLUMN pct_mobility_difficulty SET OPTIONS (
    description = 'Modeled crude prevalence (%) of adults aged >=18 reporting serious difficulty walking or climbing stairs from CDC PLACES (renamed from raw column mobility_crudeprev_, which has a trailing underscore in the upstream CDC release).'
  ),
  ALTER COLUMN pct_selfcare_difficulty SET OPTIONS (
    description = 'Modeled crude prevalence (%) of adults aged >=18 reporting difficulty dressing or bathing from CDC PLACES (source: selfcare_crudeprev).'
  ),
  ALTER COLUMN pct_indep_living_difficulty SET OPTIONS (
    description = 'Modeled crude prevalence (%) of adults aged >=18 reporting difficulty doing errands alone such as visiting a doctor office or shopping from CDC PLACES (source: indeplive_crudeprev). Indicates need for mobile or home-proximate care.'
  ),
  ALTER COLUMN pct_any_disability SET OPTIONS (
    description = 'Modeled crude prevalence (%) of adults aged >=18 with any disability (hearing, vision, cognitive, mobility, self-care, or independent living) from CDC PLACES (source: disability_crudeprev).'
  ),
  ALTER COLUMN longitude SET OPTIONS (
    description = 'Longitude (decimal degrees, WGS84) of the census tract centroid extracted from the CDC PLACES 2020-vintage geolocation point. Used for straight-line distance calculations to care sites.'
  ),
  ALTER COLUMN latitude SET OPTIONS (
    description = 'Latitude (decimal degrees, WGS84) of the census tract centroid extracted from the CDC PLACES 2020-vintage geolocation point. Used for straight-line distance calculations to care sites.'
  ),
  ALTER COLUMN svi_total_pop SET OPTIONS (
    description = 'Total population estimate for the census tract from CDC/ATSDR SVI 2022 (ACS 5-year estimate E_TOTPOP; raw -999 sentinel values converted to NULL).'
  ),
  ALTER COLUMN pct_no_vehicle SET OPTIONS (
    description = 'Percentage (%) of households in the census tract with no vehicle available from CDC/ATSDR SVI 2022 (source: EP_NOVEH; -999 sentinels converted to NULL). Measures household vehicle ownership and is populated across all 50 states, making it the reliable fallback when PLACES pct_lack_transport is NULL.'
  ),
  ALTER COLUMN pctile_no_vehicle SET OPTIONS (
    description = 'National percentile rank (0.0 to 1.0) of the percentage of households with no vehicle available from CDC/ATSDR SVI 2022 (source: EPL_NOVEH; -999 sentinels converted to NULL).'
  ),
  ALTER COLUMN pct_disability_svi SET OPTIONS (
    description = 'Percentage (%) of the civilian non-institutionalized population with a disability from CDC/ATSDR SVI 2022 ACS estimates (source: EP_DISABL; -999 sentinels converted to NULL). Direct ACS survey estimate complementing the modeled PLACES pct_any_disability.'
  ),
  ALTER COLUMN pct_age_65_plus SET OPTIONS (
    description = 'Percentage (%) of persons aged 65 and older in the census tract from CDC/ATSDR SVI 2022 (source: EP_AGE65; -999 sentinels converted to NULL).'
  ),
  ALTER COLUMN pct_age_17_under SET OPTIONS (
    description = 'Percentage (%) of persons aged 17 and younger in the census tract from CDC/ATSDR SVI 2022 (source: EP_AGE17; -999 sentinels converted to NULL).'
  ),
  ALTER COLUMN pct_uninsured_all_ages SET OPTIONS (
    description = 'Percentage (%) of the total civilian non-institutionalized population (all ages, including children and seniors 65+) without health insurance from CDC/ATSDR SVI 2022 (source: EP_UNINSUR; -999 sentinels converted to NULL). Compare with pct_uninsured (adults 18-64) to see the Medicare effect.'
  ),
  ALTER COLUMN pctile_uninsured SET OPTIONS (
    description = 'National percentile rank (0.0 to 1.0) of the all-ages uninsured rate from CDC/ATSDR SVI 2022 (source: EPL_UNINSUR; -999 sentinels converted to NULL).'
  ),
  ALTER COLUMN pct_limited_english SET OPTIONS (
    description = 'Percentage (%) of persons aged 5 and older who speak English "less than well" from CDC/ATSDR SVI 2022 (source: EP_LIMENG; -999 sentinels converted to NULL). Used to determine multilingual staffing and outreach needs for mobile clinic deployments.'
  ),
  ALTER COLUMN pct_mobile_homes SET OPTIONS (
    description = 'Percentage (%) of housing structures in the census tract that are mobile homes from CDC/ATSDR SVI 2022 (source: EP_MOBILE; -999 sentinels converted to NULL).'
  ),
  ALTER COLUMN pct_group_quarters SET OPTIONS (
    description = 'Percentage (%) of persons residing in institutionalized or non-institutionalized group quarters (e.g., dormitories, nursing homes, shelters, correctional facilities) from CDC/ATSDR SVI 2022 (source: EP_GROUPQ; -999 sentinels converted to NULL).'
  ),
  ALTER COLUMN pct_no_internet SET OPTIONS (
    description = 'Percentage (%) of households without a broadband internet subscription from CDC/ATSDR SVI 2022 (source: EP_NOINT; -999 sentinels converted to NULL). Indicates where telehealth and online appointment portals cannot substitute for physical mobile clinic presence.'
  ),
  ALTER COLUMN svi_socioeconomic SET OPTIONS (
    description = 'CDC/ATSDR SVI 2022 Theme 1 (Socioeconomic Status: poverty, unemployment, housing cost burden, no high school diploma, no health insurance) national percentile rank from 0.0 to 1.0 (source: RPL_THEME1; -999 sentinels converted to NULL).'
  ),
  ALTER COLUMN svi_household SET OPTIONS (
    description = 'CDC/ATSDR SVI 2022 Theme 2 (Household Characteristics: age 65+, age <=17, civilian with a disability, single-parent households, English language proficiency) national percentile rank from 0.0 to 1.0 (source: RPL_THEME2; -999 sentinels converted to NULL).'
  ),
  ALTER COLUMN svi_housing_transport SET OPTIONS (
    description = 'CDC/ATSDR SVI 2022 Theme 4 (Housing Type & Transportation: multi-unit structures, mobile homes, crowding, no vehicle, group quarters) national percentile rank from 0.0 to 1.0 (source: RPL_THEME4; -999 sentinels converted to NULL). Note: Theme 3 (Racial & Ethnic Minority Status) and overall RPL_THEMES are deliberately omitted from burden_tracts.'
  ),
  ALTER COLUMN uninsured_gap SET OPTIONS (
    description = 'Percentage-point difference (pct_uninsured - pct_uninsured_all_ages) between the PLACES working-age adult uninsured rate (ages 18-64) and the SVI all-ages uninsured rate. Because Medicare covers nearly everyone 65+, a large positive gap signals an older tract where working-age residents are uninsured while seniors are covered.'
  );

-- Note: When burden_tracts is built via notebooks/c5_01_load_explore.ipynb,
-- `pct_lack_transport` is also included:
-- ALTER TABLE `qwiklabs-gcp-04-f5825262a0a0.a4i_health.burden_tracts`
--   ALTER COLUMN pct_lack_transport SET OPTIONS (
--     description = 'Modeled crude prevalence (%) of adults aged >=18 lacking reliable transportation in the past 12 months from CDC PLACES (source: lacktrpt_crudeprev). MISSINGNESS WARNING: Published by CDC for 40 states only; 100% NULL in 11 states (CO, FL, KY, OR, PA, SD, TN, TX, VT, WA, WY). Fall back to SVI pct_no_vehicle when NULL.'
--   );


-- =============================================================================
-- 2. TABLE: exposure_tracts
-- =============================================================================
ALTER TABLE `qwiklabs-gcp-04-f5825262a0a0.a4i_health.exposure_tracts`
SET OPTIONS (
  description = 'Annual PM2.5 air quality summary for 2021 keyed by 2020 census tract (source: CDC Environmental Public Health Tracking vpk8-vfhm). RESOLUTION WARNING: Although keyed by census tract, values come from an EPA 12-km atmospheric grid projected onto tract centroids; neighboring tracts share identical or near-identical values and cannot support neighborhood-to-neighborhood air quality claims. Upstream duplicate daily rows have been corrected by dividing exceedance day counts by the measured publication multiplier, and transposed source lat/lon coordinates were discarded.'
);

ALTER TABLE `qwiklabs-gcp-04-f5825262a0a0.a4i_health.exposure_tracts`
  ALTER COLUMN geo_id SET OPTIONS (
    description = '11-character 2020 Census tract FIPS code (zero-padded STRING). Note: exposure_tracts contains slightly more rows than burden_tracts because the EPA 12-km grid projects onto uninhabited or low-population tracts (e.g., airports, industrial parks) that PLACES suppresses; always LEFT JOIN from burden_tracts.'
  ),
  ALTER COLUMN mean_pm SET OPTIONS (
    description = 'Annual mean of daily modeled PM2.5 concentration (ug/m3) in 2021 from the EPA 12-km downscaler model projected onto the tract centroid. Smooth across a county (typical p90/p10 ratio ~1.03); use as a county-wide baseline rather than a tract-level differentiator.'
  ),
  ALTER COLUMN max_pm SET OPTIONS (
    description = 'Highest single-day modeled PM2.5 concentration (ug/m3) in 2021 at the tract centroid from the EPA 12-km grid. Captures acute smoke or inversion spikes.'
  ),
  ALTER COLUMN days_over_12 SET OPTIONS (
    description = 'Number of distinct days in 2021 where daily modeled PM2.5 exceeded 12 ug/m3 (the pre-2024 EPA primary annual NAAQS threshold), corrected for the upstream 2x duplicate-row publication defect.'
  ),
  ALTER COLUMN days_over_20 SET OPTIONS (
    description = 'Number of distinct days in 2021 where daily modeled PM2.5 exceeded 20 ug/m3, corrected for the upstream 2x duplicate-row publication defect. Tail exceedance counts vary more across a county than mean_pm.'
  ),
  ALTER COLUMN days_over_25 SET OPTIONS (
    description = 'Number of distinct days in 2021 where daily modeled PM2.5 exceeded 25 ug/m3, corrected for the upstream 2x duplicate-row publication defect.'
  ),
  ALTER COLUMN days_over_35 SET OPTIONS (
    description = 'Number of distinct days in 2021 where daily modeled PM2.5 exceeded 35 ug/m3 (the EPA 24-hour NAAQS threshold), corrected for the upstream 2x duplicate-row publication defect.'
  );


-- =============================================================================
-- 3. TABLE: care_sites
-- =============================================================================
ALTER TABLE `qwiklabs-gcp-04-f5825262a0a0.a4i_health.care_sites`
SET OPTIONS (
  description = 'Federally recognized healthcare facilities located within the target county boundary (1 row per facility, spatially filtered from care_sites_state via ST_CONTAINS against bigquery-public-data.geo_us_boundaries.counties). Sourced from the HRSA Data Warehouse MapServices Layer 4 (CMS-certified Hospitals, Critical Access Hospitals, FQHCs, Rural Health Clinics) and Layer 0 (HRSA Health Center service delivery sites). SCOPE WARNING: Excludes non-federal free clinics, county health department clinics without FQHC/CMS status, urgent care centers, and pharmacies.'
);

ALTER TABLE `qwiklabs-gcp-04-f5825262a0a0.a4i_health.care_sites`
  ALTER COLUMN CMS_PROVIDER_NUM SET OPTIONS (
    description = 'CMS Certification Number (CCN) for Layer 4 CMS-certified facilities (Hospitals, Critical Access Hospitals, FQHCs, Rural Health Clinics); NULL for Layer 0 HRSA Health Center service delivery sites.'
  ),
  ALTER COLUMN FACILITY_NM SET OPTIONS (
    description = 'Official facility or clinic site name as registered with CMS or HRSA (standardized from FACILITY_NM on Layer 4 and SITE_NM on Layer 0).'
  ),
  ALTER COLUMN CMS_PROVIDER_ADDRESS SET OPTIONS (
    description = 'Street address of the care facility (standardized from CMS_PROVIDER_ADDRESS on Layer 4 and SITE_ADDRESS on Layer 0).'
  ),
  ALTER COLUMN CMS_PROVIDER_CITY SET OPTIONS (
    description = 'City name of the care facility (standardized from CMS_PROVIDER_CITY on Layer 4 and SITE_CITY on Layer 0).'
  ),
  ALTER COLUMN CMS_PROVIDER_STATE_ABBR SET OPTIONS (
    description = 'Two-letter US state postal abbreviation of the care facility.'
  ),
  ALTER COLUMN CMS_PROVIDER_ZIP_CD SET OPTIONS (
    description = 'ZIP code of the care facility.'
  ),
  ALTER COLUMN CMS_PROVIDER_CAT_DESC SET OPTIONS (
    description = 'CMS provider category description (e.g., Hospital, Critical Access Hospital, Federally Qualified Health Center, Rural Health Clinic) for Layer 4 rows; NULL for Layer 0 Health Center sites.'
  ),
  ALTER COLUMN CMS_PROVIDER_CAT_SUB_TYP_DESC SET OPTIONS (
    description = 'CMS provider category subtype description for Layer 4 facilities; NULL for Layer 0 Health Center sites.'
  ),
  ALTER COLUMN longitude SET OPTIONS (
    description = 'Facility point longitude (decimal degrees, WGS84) extracted from the HRSA ArcGIS geometry point.'
  ),
  ALTER COLUMN latitude SET OPTIONS (
    description = 'Facility point latitude (decimal degrees, WGS84) extracted from the HRSA ArcGIS geometry point.'
  ),
  ALTER COLUMN site_kind SET OPTIONS (
    description = 'Harmonized facility classification across HRSA layers: "Hospital", "Critical Access Hospital", "FQHC", or "Rural Health Clinic" (from Layer 4), or "Health Center site" (from Layer 0). Note: Safety-net sites accepting uninsured patients on a sliding fee scale correspond to site_kind IN ("FQHC", "Health Center site").'
  ),
  ALTER COLUMN HCC_TYP_DESC SET OPTIONS (
    description = 'HRSA Health Center type description (e.g., Service Delivery Site, Administrative/Service Delivery Site) populated for Layer 0 Health Center sites; NULL for Layer 4 CMS facilities.'
  ),
  ALTER COLUMN HCC_STATUS_DESC SET OPTIONS (
    description = 'Operational status description of the HRSA Health Center site (e.g., Active); NULL for Layer 4 CMS facilities.'
  ),
  ALTER COLUMN HCC_LOC_SETTING_DESC SET OPTIONS (
    description = 'Location setting description for HRSA Health Center sites (e.g., All Other Clinic Types, School, Mobile Van, Domestic Violence Shelter); NULL for Layer 4 CMS facilities. Check this column to avoid treating school-restricted or mobile vans as full-time walk-in bricks-and-mortar clinics.'
  ),
  ALTER COLUMN TOT_OPER_HR_PER_WEEK SET OPTIONS (
    description = 'Total operating hours per week reported for HRSA Layer 0 Health Center sites; NULL for Layer 4 CMS facilities. Crucial for verifying real access capacity: many listed safety-net sites operate only a few hours per week.'
  ),
  ALTER COLUMN SITE_POP_TYP_DESC SET OPTIONS (
    description = 'Target population type description for HRSA Layer 0 Health Center sites; NULL for Layer 4 CMS facilities.'
  ),
  ALTER COLUMN RURAL_IND SET OPTIONS (
    description = 'Rural status indicator ("Yes"/"No") reported by HRSA Layer 0 for Health Center sites; NULL for Layer 4 CMS facilities.'
  ),
  ALTER COLUMN MHC_SUB_PROG_IND SET OPTIONS (
    description = 'Migrant Health Center (MHC) sub-program grant indicator ("Yes"/"No") for HRSA Layer 0 Health Center sites; NULL for Layer 4 CMS facilities.'
  ),
  ALTER COLUMN SBHC_SUB_PROG_IND SET OPTIONS (
    description = 'School-Based Health Center (SBHC) sub-program indicator ("Yes"/"No") for HRSA Layer 0 Health Center sites; NULL for Layer 4 CMS facilities. Sites with SBHC_SUB_PROG_IND = "Yes" primarily serve enrolled students rather than the general adult community.'
  ),
  ALTER COLUMN PHPC_SUB_PROG_IND SET OPTIONS (
    description = 'Public Housing Primary Care (PHPC) sub-program grant indicator ("Yes"/"No") for HRSA Layer 0 Health Center sites; NULL for Layer 4 CMS facilities.'
  ),
  ALTER COLUMN HCH_SUB_PROG_IND SET OPTIONS (
    description = 'Health Care for the Homeless (HCH) sub-program grant indicator ("Yes"/"No") for HRSA Layer 0 Health Center sites; NULL for Layer 4 CMS facilities.'
  ),
  ALTER COLUMN county_geo_id SET OPTIONS (
    description = '5-character state+county FIPS code (e.g., "13121" for Fulton County, GA) assigned via spatial point-in-polygon join (ST_CONTAINS) against bigquery-public-data.geo_us_boundaries.counties.'
  ),
  ALTER COLUMN county_name SET OPTIONS (
    description = 'County name assigned via spatial point-in-polygon join (ST_CONTAINS) against bigquery-public-data.geo_us_boundaries.counties.'
  );


-- =============================================================================
-- 4. TABLE: care_sites_state
-- =============================================================================
ALTER TABLE `qwiklabs-gcp-04-f5825262a0a0.a4i_health.care_sites_state`
SET OPTIONS (
  description = 'All federally recognized healthcare facilities across the entire state (1 row per facility, prior to county polygon filtering). Combines HRSA MapServices Layer 4 (CMS-certified Hospitals, Critical Access Hospitals, FQHCs, Rural Health Clinics) and Layer 0 (HRSA Health Center service delivery sites). Essential for detecting cross-border care access where a tract near a county boundary is closer to a safety-net clinic in an adjacent county than to any clinic inside its own county.'
);

ALTER TABLE `qwiklabs-gcp-04-f5825262a0a0.a4i_health.care_sites_state`
  ALTER COLUMN CMS_PROVIDER_NUM SET OPTIONS (
    description = 'CMS Certification Number (CCN) for Layer 4 CMS-certified facilities; NULL for Layer 0 HRSA Health Center service delivery sites.'
  ),
  ALTER COLUMN FACILITY_NM SET OPTIONS (
    description = 'Official facility or clinic site name as registered with CMS or HRSA.'
  ),
  ALTER COLUMN CMS_PROVIDER_ADDRESS SET OPTIONS (
    description = 'Street address of the care facility.'
  ),
  ALTER COLUMN CMS_PROVIDER_CITY SET OPTIONS (
    description = 'City name of the care facility.'
  ),
  ALTER COLUMN CMS_PROVIDER_STATE_ABBR SET OPTIONS (
    description = 'Two-letter US state postal abbreviation of the care facility.'
  ),
  ALTER COLUMN CMS_PROVIDER_ZIP_CD SET OPTIONS (
    description = 'ZIP code of the care facility.'
  ),
  ALTER COLUMN CMS_PROVIDER_CAT_DESC SET OPTIONS (
    description = 'CMS provider category description for Layer 4 facilities; NULL for Layer 0 Health Center sites.'
  ),
  ALTER COLUMN CMS_PROVIDER_CAT_SUB_TYP_DESC SET OPTIONS (
    description = 'CMS provider category subtype description for Layer 4 facilities; NULL for Layer 0 Health Center sites.'
  ),
  ALTER COLUMN longitude SET OPTIONS (
    description = 'Facility point longitude (decimal degrees, WGS84) extracted from the HRSA ArcGIS geometry point.'
  ),
  ALTER COLUMN latitude SET OPTIONS (
    description = 'Facility point latitude (decimal degrees, WGS84) extracted from the HRSA ArcGIS geometry point.'
  ),
  ALTER COLUMN site_kind SET OPTIONS (
    description = 'Harmonized facility classification: "Hospital", "Critical Access Hospital", "FQHC", or "Rural Health Clinic" (from Layer 4), or "Health Center site" (from Layer 0). Filter to site_kind IN ("FQHC", "Health Center site") for sliding-scale safety-net primary care.'
  ),
  ALTER COLUMN HCC_TYP_DESC SET OPTIONS (
    description = 'HRSA Health Center type description for Layer 0 Health Center sites; NULL for Layer 4 CMS facilities.'
  ),
  ALTER COLUMN HCC_STATUS_DESC SET OPTIONS (
    description = 'Operational status description of the HRSA Health Center site; NULL for Layer 4 CMS facilities.'
  ),
  ALTER COLUMN HCC_LOC_SETTING_DESC SET OPTIONS (
    description = 'Location setting description for HRSA Health Center sites (e.g., All Other Clinic Types, School, Mobile Van); NULL for Layer 4 CMS facilities.'
  ),
  ALTER COLUMN TOT_OPER_HR_PER_WEEK SET OPTIONS (
    description = 'Total operating hours per week reported for HRSA Layer 0 Health Center sites; NULL for Layer 4 CMS facilities.'
  ),
  ALTER COLUMN SITE_POP_TYP_DESC SET OPTIONS (
    description = 'Target population type description for HRSA Layer 0 Health Center sites; NULL for Layer 4 CMS facilities.'
  ),
  ALTER COLUMN RURAL_IND SET OPTIONS (
    description = 'Rural status indicator ("Yes"/"No") for HRSA Layer 0 Health Center sites; NULL for Layer 4 CMS facilities.'
  ),
  ALTER COLUMN MHC_SUB_PROG_IND SET OPTIONS (
    description = 'Migrant Health Center (MHC) sub-program grant indicator ("Yes"/"No") for HRSA Layer 0 Health Center sites; NULL for Layer 4 CMS facilities.'
  ),
  ALTER COLUMN SBHC_SUB_PROG_IND SET OPTIONS (
    description = 'School-Based Health Center (SBHC) sub-program indicator ("Yes"/"No") for HRSA Layer 0 Health Center sites; NULL for Layer 4 CMS facilities.'
  ),
  ALTER COLUMN PHPC_SUB_PROG_IND SET OPTIONS (
    description = 'Public Housing Primary Care (PHPC) sub-program grant indicator ("Yes"/"No") for HRSA Layer 0 Health Center sites; NULL for Layer 4 CMS facilities.'
  ),
  ALTER COLUMN HCH_SUB_PROG_IND SET OPTIONS (
    description = 'Health Care for the Homeless (HCH) sub-program grant indicator ("Yes"/"No") for HRSA Layer 0 Health Center sites; NULL for Layer 4 CMS facilities.'
  );


-- =============================================================================
-- 5. TABLE: shortage_areas
-- =============================================================================
ALTER TABLE `qwiklabs-gcp-04-f5825262a0a0.a4i_health.shortage_areas`
SET OPTIONS (
  description = 'Active HRSA Primary Care Health Professional Shortage Area (HPSA) geographic and population designations (Layer 11, filtered to HPSA_STATUS_DESC = "Designated", excluding "Proposed For Withdrawal"). Represents underserved neighborhoods/counties lacking sufficient primary care providers (a positive siting signal for mobile clinics). COVERAGE WARNING: Legitimately 0 rows in Fulton (GA), Santa Clara (CA), Harris (TX), and Travis (TX) because HRSA designates clinics as facility HPSAs (in shortage_facilities) rather than geographic tracts in those counties. Never UNION with shortage_facilities.'
);

ALTER TABLE `qwiklabs-gcp-04-f5825262a0a0.a4i_health.shortage_areas`
  ALTER COLUMN HPSA_NM SET OPTIONS (
    description = 'Name of the HRSA-designated Primary Care Health Professional Shortage Area (geographic area or low-income/medically underserved population group).'
  ),
  ALTER COLUMN HPSA_SCORE SET OPTIONS (
    description = 'HRSA Primary Care HPSA severity score ranging from 0 to 25 (higher means more severe shortage). Incorporates population-to-provider ratio (up to 10 pts), percent below 100% federal poverty level (up to 5 pts), Infant Health Index (up to 5 pts), and travel time/distance to the nearest source of nondiscriminatory care (up to 5 pts).'
  );

-- Note: When `shortage_areas` is populated in counties with geographic HPSA rows
-- (or built via notebooks/c5_01_load_explore.ipynb), the following additional
-- columns are present and can be documented with:
-- ALTER TABLE `qwiklabs-gcp-04-f5825262a0a0.a4i_health.shortage_areas`
--   ALTER COLUMN HPSA_STATUS_DESC SET OPTIONS (description = 'HPSA designation status description, filtered to "Designated" (active designations only; "Proposed For Withdrawal" rows are excluded).'),
--   ALTER COLUMN HPSA_TYP_DESC SET OPTIONS (description = 'Type of geographic or population HPSA designation (e.g., Geographic HPSA, High Needs Geographic HPSA, Low Income Population HPSA).'),
--   ALTER COLUMN HPSA_DESIGNATION_POP SET OPTIONS (description = 'Total population covered by the HPSA designation.'),
--   ALTER COLUMN HPSA_ESTIMATED_UNDERSERVED_POP SET OPTIONS (description = 'HRSA-estimated number of underserved residents within the HPSA component.'),
--   ALTER COLUMN HPSA_ESTIMATED_SERVED_POP SET OPTIONS (description = 'HRSA-estimated number of residents currently served by available primary care providers in the HPSA component.'),
--   ALTER COLUMN HPSA_POVERTY SET OPTIONS (description = 'Percentage (%) of the HPSA designation population with household income below 100% of the Federal Poverty Level.'),
--   ALTER COLUMN HPSA_FORMAL_RATIO SET OPTIONS (description = 'Formal population-to-full-time-equivalent-primary-care-physician ratio (e.g., "4250:1") used in the HRSA HPSA score calculation.'),
--   ALTER COLUMN GEO_ID SET OPTIONS (description = 'Component geographic FIPS identifier. MIXED GRAIN WARNING: Can be either an 11-character census tract FIPS code (in urban counties) or a 5-character state+county FIPS code (in whole-county rural designations). Check geo_id_len before joining to tract tables.'),
--   ALTER COLUMN STATE_COUNTY_FIPS_CD SET OPTIONS (description = '5-character state+county FIPS code of the HPSA component.'),
--   ALTER COLUMN COUNTY_NM SET OPTIONS (description = 'County name of the HPSA component.'),
--   ALTER COLUMN RURAL_STATUS_DESC SET OPTIONS (description = 'HRSA rurality classification of the HPSA component (e.g., Non-Rural, Rural, Partially Rural).'),
--   ALTER COLUMN HPSA_DESIGNATION_DT SET OPTIONS (description = 'Date the HPSA component was officially designated by HRSA.'),
--   ALTER COLUMN geo_id_len SET OPTIONS (description = 'Character length of GEO_ID (11 = census-tract-level designation; 5 = whole-county designation). Filter on geo_id_len = 11 before joining GEO_ID to burden_tracts.geo_id.');


-- =============================================================================
-- 6. TABLE: shortage_facilities
-- =============================================================================
ALTER TABLE `qwiklabs-gcp-04-f5825262a0a0.a4i_health.shortage_facilities`
SET OPTIONS (
  description = 'HRSA HPSA-designated facilities (Layer 9, filtered to discipline "Primary Care" and active status "Designated"). CRITICAL DIRECTIONALITY WARNING: Despite the "shortage" prefix, this table lists existing clinics, FQHCs (auto-designated under Section 330), rural health clinics, and state/federal correctional facilities that serve an underserved population—meaning it marks where care supply ALREADY EXISTS. Never UNION this table with shortage_areas; a neighborhood far from shortage_facilities is underserved, whereas a point inside shortage_facilities already has a facility.'
);

ALTER TABLE `qwiklabs-gcp-04-f5825262a0a0.a4i_health.shortage_facilities`
  ALTER COLUMN HPSA_NM SET OPTIONS (
    description = 'Name of the HPSA-designated facility (e.g., FQHC clinic, hospital outpatient site, or correctional institution).'
  ),
  ALTER COLUMN HPSA_TYP_DESC SET OPTIONS (
    description = 'HPSA facility type description (e.g., Comprehensive Health Center, Federally Qualified Health Center Look A Like, Rural Health Clinic, Correctional Facility). Filter out "%Correctional%" when evaluating community primary care access.'
  ),
  ALTER COLUMN HPSA_POPULATION_TYP_DESC SET OPTIONS (
    description = 'Population type served by the HPSA-designated facility.'
  ),
  ALTER COLUMN HPSA_SCORE SET OPTIONS (
    description = 'HRSA Primary Care HPSA score (0 to 25) assigned to the facility for NHSC clinician loan repayment and recruitment priority.'
  ),
  ALTER COLUMN HPSA_STATUS_DESC SET OPTIONS (
    description = 'HPSA designation status of the facility, filtered to "Designated" (active).'
  ),
  ALTER COLUMN ADDRESS SET OPTIONS (
    description = 'Street address of the HPSA-designated facility.'
  ),
  ALTER COLUMN CITY SET OPTIONS (
    description = 'City of the HPSA-designated facility.'
  ),
  ALTER COLUMN ZIP_CD SET OPTIONS (
    description = 'ZIP code of the HPSA-designated facility.'
  ),
  ALTER COLUMN HPSA_DESIGNATION_POP SET OPTIONS (
    description = 'Target population count associated with the facility HPSA designation (often NULL for auto-designated FQHCs).'
  ),
  ALTER COLUMN RURAL_STATUS_DESC SET OPTIONS (
    description = 'Rurality classification of the HPSA-designated facility (e.g., Non-Rural, Rural).'
  ),
  ALTER COLUMN CMN_STATE_COUNTY_FIPS_CD SET OPTIONS (
    description = '5-character state+county FIPS code for the facility (note column name spelling differs from STATE_COUNTY_FIPS_CD in shortage_areas).'
  ),
  ALTER COLUMN longitude SET OPTIONS (
    description = 'Facility point longitude (decimal degrees, WGS84) extracted from the HRSA Layer 9 ArcGIS geometry point.'
  ),
  ALTER COLUMN latitude SET OPTIONS (
    description = 'Facility point latitude (decimal degrees, WGS84) extracted from the HRSA Layer 9 ArcGIS geometry point.'
  );


-- =============================================================================
-- 7. TABLE: disease_weekly
-- =============================================================================
ALTER TABLE `qwiklabs-gcp-04-f5825262a0a0.a4i_health.disease_weekly`
SET OPTIONS (
  description = 'Weekly emergency department (ED) respiratory illness visit percentages and trajectory trends for COVID-19, Influenza, and RSV from CDC NSSP (dataset rda8-686k, filtered to exclude state-wide county = "All" rollup rows). SPATIAL RESOLUTION WARNING: Although keyed by county fips, values are computed at the multi-county Health Service Area (hsa) level and copied identically onto every county in that HSA. Cannot differentiate neighborhoods or individual counties within the same HSA. MISSINGNESS WARNING: All numeric visit percentage columns are 100% NULL in Santa Clara (CA) and Bronx (NY) where trend_source = "Data Unavailable".'
);

ALTER TABLE `qwiklabs-gcp-04-f5825262a0a0.a4i_health.disease_weekly`
  ALTER COLUMN week_end SET OPTIONS (
    description = 'End timestamp of the CDC MMWR surveillance week (1 row per week for the target county).'
  ),
  ALTER COLUMN geography SET OPTIONS (
    description = 'State or jurisdiction name (e.g., "Georgia") reported in the CDC NSSP respiratory surveillance dataset.'
  ),
  ALTER COLUMN county SET OPTIONS (
    description = 'County name (e.g., "Fulton"). State-level aggregate rows where county = "All" have been excluded.'
  ),
  ALTER COLUMN fips SET OPTIONS (
    description = 'County FIPS identifier from the upstream CDC NSSP table. FORMATTING WARNING: Upstream Socrata stores fips as a number, which strips the leading zero for states with FIPS < 10 (e.g., "6085" instead of "06085"). Always LPAD(CAST(fips AS STRING), 5, "0") before joining.'
  ),
  ALTER COLUMN hsa SET OPTIONS (
    description = 'Health Service Area (HSA) name or identifier—the true spatial unit of aggregation at which CDC NSSP calculates emergency department respiratory visit percentages.'
  ),
  ALTER COLUMN hsa_counties SET OPTIONS (
    description = 'List of all counties pooled into the Health Service Area (hsa) that share the exact same respiratory visit percentages and trend values (e.g., 4 counties for Fulton, GA; 6 counties for Travis, TX).'
  ),
  ALTER COLUMN trend_source SET OPTIONS (
    description = 'Data source level for the respiratory trend metrics (e.g., "HSA", "County", or "Data Unavailable"). When trend_source = "Data Unavailable" (as in Santa Clara and the Bronx), all percentage columns are NULL.'
  ),
  ALTER COLUMN percent_visits_combined SET OPTIONS (
    description = 'Un-smoothed percentage (%) of all emergency department visits in the HSA during the week attributed to combined respiratory illnesses (COVID-19, Influenza, and RSV).'
  ),
  ALTER COLUMN percent_visits_covid SET OPTIONS (
    description = 'Un-smoothed percentage (%) of all emergency department visits in the HSA during the week with a diagnosed COVID-19 discharge code.'
  ),
  ALTER COLUMN percent_visits_influenza SET OPTIONS (
    description = 'Un-smoothed percentage (%) of all emergency department visits in the HSA during the week with a diagnosed Influenza discharge code.'
  ),
  ALTER COLUMN percent_visits_rsv SET OPTIONS (
    description = 'Un-smoothed percentage (%) of all emergency department visits in the HSA during the week with a diagnosed Respiratory Syncytial Virus (RSV) discharge code.'
  ),
  ALTER COLUMN percent_visits_smoothed_combined SET OPTIONS (
    description = ' temporally smoothed percentage (%) of emergency department visits in the HSA attributed to combined COVID-19, Influenza, and RSV (renamed from ambiguous raw Socrata column percent_visits_smoothed).'
  ),
  ALTER COLUMN percent_visits_smoothed_covid SET OPTIONS (
    description = 'Temporally smoothed percentage (%) of emergency department visits in the HSA attributed to COVID-19.'
  ),
  ALTER COLUMN percent_visits_smoothed_influenza SET OPTIONS (
    description = 'Temporally smoothed percentage (%) of emergency department visits in the HSA attributed to Influenza (renamed from ambiguous raw Socrata duplicate-header column percent_visits_smoothed_1).'
  ),
  ALTER COLUMN percent_visits_smoothed_rsv SET OPTIONS (
    description = 'Temporally smoothed percentage (%) of emergency department visits in the HSA attributed to RSV.'
  ),
  ALTER COLUMN ed_trends_covid SET OPTIONS (
    description = 'Categorical week-over-week trajectory classification for COVID-19 emergency department visits in the HSA (e.g., Increasing, Decreasing, No Change, or Data Unavailable).'
  ),
  ALTER COLUMN ed_trends_influenza SET OPTIONS (
    description = 'Categorical week-over-week trajectory classification for Influenza emergency department visits in the HSA (e.g., Increasing, Decreasing, No Change, or Data Unavailable).'
  ),
  ALTER COLUMN ed_trends_rsv SET OPTIONS (
    description = 'Categorical week-over-week trajectory classification for RSV emergency department visits in the HSA (e.g., Increasing, Decreasing, No Change, or Data Unavailable).'
  );


-- =============================================================================
-- 8. TABLE: tract_access
-- =============================================================================
ALTER TABLE `qwiklabs-gcp-04-f5825262a0a0.a4i_health.tract_access`
SET OPTIONS (
  description = 'Pre-computed census-tract healthcare access distance table (1 row per census tract in burden_tracts). Cross-joins tract centroids from burden_tracts against facility points in care_sites to measure straight-line distance to any federally recognized care site vs. the nearest sliding-scale safety-net clinic (FQHC or HRSA Health Center site). CAVEAT: Distances are straight-line within-county upper bounds on federally listed sites (excludes non-federal charity clinics and clinics just across a county line; compare with care_sites_state / audit_tract_diagnostics for cross-border effects).'
);

ALTER TABLE `qwiklabs-gcp-04-f5825262a0a0.a4i_health.tract_access`
  ALTER COLUMN geo_id SET OPTIONS (
    description = '11-character 2020 Census tract FIPS code (zero-padded STRING). Joins 1:1 with burden_tracts.geo_id.'
  ),
  ALTER COLUMN total_pop SET OPTIONS (
    description = 'Total resident population of the census tract from CDC PLACES (burden_tracts.total_pop).'
  ),
  ALTER COLUMN pct_uninsured SET OPTIONS (
    description = 'Modeled crude prevalence (%) of uninsured working-age adults (aged 18-64) from CDC PLACES (burden_tracts.pct_uninsured).'
  ),
  ALTER COLUMN pct_asthma SET OPTIONS (
    description = 'Modeled crude prevalence (%) of current adult asthma from CDC PLACES (burden_tracts.pct_asthma).'
  ),
  ALTER COLUMN pct_diabetes SET OPTIONS (
    description = 'Modeled crude prevalence (%) of diagnosed adult diabetes from CDC PLACES (burden_tracts.pct_diabetes).'
  ),
  ALTER COLUMN pct_no_vehicle SET OPTIONS (
    description = 'Percentage (%) of households with no vehicle available from CDC/ATSDR SVI 2022 (burden_tracts.pct_no_vehicle).'
  ),
  ALTER COLUMN pct_age_65_plus SET OPTIONS (
    description = 'Percentage (%) of tract residents aged 65 and older from CDC/ATSDR SVI 2022 (burden_tracts.pct_age_65_plus).'
  ),
  ALTER COLUMN km_to_any_care SET OPTIONS (
    description = 'Minimum straight-line distance in kilometers (ST_DISTANCE / 1000) from the census tract centroid to the nearest federally recognized care facility of any site_kind in care_sites within the county.'
  ),
  ALTER COLUMN km_to_safety_net SET OPTIONS (
    description = 'Minimum straight-line distance in kilometers (ST_DISTANCE / 1000) from the census tract centroid to the nearest safety-net primary care facility (site_kind IN ("FQHC", "Health Center site")) in care_sites within the county.'
  ),
  ALTER COLUMN extra_km_if_uninsured SET OPTIONS (
    description = 'Additional straight-line distance in kilometers (km_to_safety_net - km_to_any_care) that an uninsured or sliding-fee-reliant resident must travel past the nearest general healthcare facility to reach the nearest safety-net clinic (FQHC or HRSA Health Center site).'
  );


-- =============================================================================
-- 9. TABLE: synthetic_shortage_tracts
-- =============================================================================
ALTER TABLE `qwiklabs-gcp-04-f5825262a0a0.a4i_health.synthetic_shortage_tracts`
SET OPTIONS (
  description = 'Tract-level synthetic shortage area scoring and cross-border clinic distance table (1 row per census tract). Created to address counties like Fulton (GA), Santa Clara (CA), Harris (TX), and Travis (TX) where HRSA geographic shortage_areas has 0 rows because designations were filed as facility HPSAs in shortage_facilities. Combines socioeconomic/transport barriers (35%), vehicle-adjusted safety-net distance (35%), and chronic/preventive burden (30%) into a 0-100 synthetic_shortage_score while checking statewide cross-border clinics in care_sites_state.'
);

ALTER TABLE `qwiklabs-gcp-04-f5825262a0a0.a4i_health.synthetic_shortage_tracts`
  ALTER COLUMN geo_id SET OPTIONS (
    description = '11-character 2020 Census tract FIPS code (zero-padded STRING).'
  ),
  ALTER COLUMN total_pop SET OPTIONS (
    description = 'Total resident population of the census tract from CDC PLACES.'
  ),
  ALTER COLUMN longitude SET OPTIONS (
    description = 'Longitude (decimal degrees, WGS84) of the census tract centroid.'
  ),
  ALTER COLUMN latitude SET OPTIONS (
    description = 'Latitude (decimal degrees, WGS84) of the census tract centroid.'
  ),
  ALTER COLUMN km_to_any_care SET OPTIONS (
    description = 'Straight-line distance (km) from tract centroid to the nearest federally recognized care facility of any kind within the county (from tract_access).'
  ),
  ALTER COLUMN km_to_safety_net SET OPTIONS (
    description = 'Straight-line distance (km) from tract centroid to the nearest within-county safety-net clinic (FQHC or Health Center site) from tract_access.'
  ),
  ALTER COLUMN extra_km_if_uninsured SET OPTIONS (
    description = 'Additional straight-line distance (km_to_safety_net - km_to_any_care) to reach a within-county safety-net clinic compared to any care facility.'
  ),
  ALTER COLUMN km_to_shortage_facility SET OPTIONS (
    description = 'Straight-line distance (km) from tract centroid to the nearest non-correctional HRSA HPSA-designated facility in shortage_facilities (falls back to km_to_safety_net if NULL).'
  ),
  ALTER COLUMN km_to_safety_net_statewide SET OPTIONS (
    description = 'Straight-line distance (km) from tract centroid to the nearest safety-net clinic (FQHC or Health Center site) anywhere in the state using care_sites_state, removing artificial county-boundary edge effects.'
  ),
  ALTER COLUMN border_km_saved_statewide SET OPTIONS (
    description = 'Distance reduction in kilometers (km_to_safety_net - km_to_safety_net_statewide) achieved when considering safety-net clinics across county lines in care_sites_state.'
  ),
  ALTER COLUMN nearest_state_safety_net_name SET OPTIONS (
    description = 'Facility name (FACILITY_NM) of the nearest safety-net clinic across the entire state from care_sites_state.'
  ),
  ALTER COLUMN nearest_safety_net_hours_wk SET OPTIONS (
    description = 'Weekly operating hours (TOT_OPER_HR_PER_WEEK) of the nearest statewide safety-net clinic from care_sites_state.'
  ),
  ALTER COLUMN pct_uninsured SET OPTIONS (
    description = 'Modeled crude prevalence (%) of uninsured adults aged 18-64 from CDC PLACES.'
  ),
  ALTER COLUMN pctile_uninsured SET OPTIONS (
    description = 'National percentile rank (0.0 to 1.0) of the all-ages uninsured rate from CDC/ATSDR SVI 2022.'
  ),
  ALTER COLUMN pct_uninsured_all_ages SET OPTIONS (
    description = 'Percentage (%) uninsured across all ages from CDC/ATSDR SVI 2022.'
  ),
  ALTER COLUMN uninsured_gap SET OPTIONS (
    description = 'Percentage-point gap (pct_uninsured - pct_uninsured_all_ages) reflecting working-age uninsurance vs. Medicare-covered seniors.'
  ),
  ALTER COLUMN pct_no_vehicle SET OPTIONS (
    description = 'Percentage (%) of households with no vehicle available from CDC/ATSDR SVI 2022.'
  ),
  ALTER COLUMN pctile_no_vehicle SET OPTIONS (
    description = 'National percentile rank (0.0 to 1.0) of households with no vehicle available from CDC/ATSDR SVI 2022.'
  ),
  ALTER COLUMN pct_checkup SET OPTIONS (
    description = 'Modeled crude prevalence (%) of adults who had a routine medical checkup in the past year from CDC PLACES (lower = worse preventive care access).'
  ),
  ALTER COLUMN pct_missed_checkup SET OPTIONS (
    description = 'Inverted routine checkup prevalence (100.0 - pct_checkup), representing the estimated percentage (%) of adults who did NOT have a routine checkup in the past year (higher = greater unmet preventive care need).'
  ),
  ALTER COLUMN pct_asthma SET OPTIONS (
    description = 'Modeled crude prevalence (%) of current adult asthma from CDC PLACES.'
  ),
  ALTER COLUMN pct_copd SET OPTIONS (
    description = 'Modeled crude prevalence (%) of adult COPD from CDC PLACES.'
  ),
  ALTER COLUMN pct_diabetes SET OPTIONS (
    description = 'Modeled crude prevalence (%) of diagnosed adult diabetes from CDC PLACES.'
  ),
  ALTER COLUMN pct_high_bp SET OPTIONS (
    description = 'Modeled crude prevalence (%) of adult high blood pressure from CDC PLACES.'
  ),
  ALTER COLUMN pct_mobility_difficulty SET OPTIONS (
    description = 'Modeled crude prevalence (%) of adult mobility difficulty from CDC PLACES.'
  ),
  ALTER COLUMN pct_any_disability SET OPTIONS (
    description = 'Modeled crude prevalence (%) of any adult disability from CDC PLACES.'
  ),
  ALTER COLUMN pct_age_65_plus SET OPTIONS (
    description = 'Percentage (%) of persons aged 65 and older from CDC/ATSDR SVI 2022.'
  ),
  ALTER COLUMN pct_age_17_under SET OPTIONS (
    description = 'Percentage (%) of persons aged 17 and younger from CDC/ATSDR SVI 2022.'
  ),
  ALTER COLUMN pct_limited_english SET OPTIONS (
    description = 'Percentage (%) of persons aged 5+ who speak English "less than well" from CDC/ATSDR SVI 2022.'
  ),
  ALTER COLUMN pct_no_internet SET OPTIONS (
    description = 'Percentage (%) of households without broadband internet from CDC/ATSDR SVI 2022.'
  ),
  ALTER COLUMN svi_socioeconomic SET OPTIONS (
    description = 'CDC/ATSDR SVI 2022 Theme 1 (Socioeconomic Status) national percentile rank (0.0 to 1.0).'
  ),
  ALTER COLUMN svi_household SET OPTIONS (
    description = 'CDC/ATSDR SVI 2022 Theme 2 (Household Characteristics) national percentile rank (0.0 to 1.0).'
  ),
  ALTER COLUMN svi_housing_transport SET OPTIONS (
    description = 'CDC/ATSDR SVI 2022 Theme 4 (Housing Type & Transportation) national percentile rank (0.0 to 1.0).'
  ),
  ALTER COLUMN synthetic_shortage_score SET OPTIONS (
    description = 'Composite 0-100 synthetic shortage score combining socioeconomic/transport barriers (35% weight on pctile_uninsured and pctile_no_vehicle), vehicle-penalized distance to a safety-net clinic (35% weight on km_to_safety_net scaled by pct_no_vehicle), and chronic/preventive health burden (30% weight on pct_missed_checkup, pct_diabetes, pct_high_bp, and pct_asthma).'
  ),
  ALTER COLUMN not_near_safety_net SET OPTIONS (
    description = 'Boolean flag (TRUE when km_to_safety_net >= 5.0 and extra_km_if_uninsured > 0) indicating the tract is at least 5 km from a county safety-net clinic and faces an uninsured distance penalty.'
  ),
  ALTER COLUMN not_near_shortage_facility SET OPTIONS (
    description = 'Boolean flag (TRUE when km_to_shortage_facility >= 5.0) indicating the tract is at least 5 km away from any non-correctional HPSA-designated facility in shortage_facilities.'
  ),
  ALTER COLUMN is_synthetic_shortage_area SET OPTIONS (
    description = 'Boolean siting flag (TRUE when synthetic_shortage_score >= 55.0) identifying census tracts that qualify as high-need synthetic primary care shortage areas.'
  ),
  ALTER COLUMN has_closer_cross_border_clinic SET OPTIONS (
    description = 'Boolean edge-effect flag (TRUE when border_km_saved_statewide >= 2.0) indicating that a safety-net clinic in a neighboring county (from care_sites_state) is at least 2 km closer than the nearest within-county safety-net clinic.'
  );


-- =============================================================================
-- 10. TABLE: audit_tract_diagnostics
-- =============================================================================
ALTER TABLE `qwiklabs-gcp-04-f5825262a0a0.a4i_health.audit_tract_diagnostics`
SET OPTIONS (
  description = 'Post-hoc equity audit, uncertainty interval, and real-world clinic capacity diagnostic table (1 row per census tract). Strictly separated from burden_tracts so racial/ethnic composition (SVI Theme 3 and ACS race/ethnicity) is never used as a siting score input, but is available after ranking to verify who is served and who is left out. Also provides CDC PLACES 95% confidence limits, full-time (>=30 hr/wk) vs. part-time/mobile/school-based safety-net distance penalties, cross-border distance savings, and named community staging corridors.'
);

ALTER TABLE `qwiklabs-gcp-04-f5825262a0a0.a4i_health.audit_tract_diagnostics`
  ALTER COLUMN geo_id SET OPTIONS (
    description = '11-character 2020 Census tract FIPS code (zero-padded STRING). Joins 1:1 with burden_tracts.geo_id.'
  ),
  ALTER COLUMN latitude SET OPTIONS (
    description = 'Latitude (decimal degrees, WGS84) of the census tract centroid.'
  ),
  ALTER COLUMN longitude SET OPTIONS (
    description = 'Longitude (decimal degrees, WGS84) of the census tract centroid.'
  ),
  ALTER COLUMN nearest_safety_net_name SET OPTIONS (
    description = 'Facility name (FACILITY_NM) of the geographically nearest within-county safety-net site (FQHC or HRSA Health Center site) in care_sites.'
  ),
  ALTER COLUMN nearest_safety_net_kind SET OPTIONS (
    description = 'Facility classification (site_kind: "FQHC" or "Health Center site") of the nearest within-county safety-net site.'
  ),
  ALTER COLUMN nearest_safety_net_hours_wk SET OPTIONS (
    description = 'Weekly operating hours (TOT_OPER_HR_PER_WEEK) of the nearest within-county safety-net site. Used to detect nominal clinics that are only open a few hours per week.'
  ),
  ALTER COLUMN nearest_sn_is_mobile_unit SET OPTIONS (
    description = 'Boolean flag indicating whether the nearest safety-net site is a mobile van rather than a permanent bricks-and-mortar clinic.'
  ),
  ALTER COLUMN nearest_sn_is_school_based SET OPTIONS (
    description = 'Boolean flag indicating whether the nearest safety-net site is a School-Based Health Center (SBHC_SUB_PROG_IND = "Yes" or school setting) restricted to students.'
  ),
  ALTER COLUMN nearest_sn_is_part_time SET OPTIONS (
    description = 'Boolean flag indicating whether the nearest safety-net site operates part-time (under 30 hours per week).'
  ),
  ALTER COLUMN km_to_county_safety_net SET OPTIONS (
    description = 'Straight-line distance (km) from the tract centroid to the nearest within-county safety-net site of any operating schedule.'
  ),
  ALTER COLUMN km_to_fulltime_safety_net SET OPTIONS (
    description = 'Straight-line distance (km) from the tract centroid to the nearest permanent, non-school-restricted safety-net clinic operating full-time (>=30 hours/week).'
  ),
  ALTER COLUMN fulltime_hours_penalty_km SET OPTIONS (
    description = 'Additional straight-line distance in kilometers (km_to_fulltime_safety_net - km_to_county_safety_net) a resident must travel when the nominally nearest safety-net site is a mobile van, school-only clinic, or part-time site.'
  ),
  ALTER COLUMN nearest_statewide_safety_net_name SET OPTIONS (
    description = 'Facility name (FACILITY_NM) of the nearest safety-net clinic across the entire state (from care_sites_state), including clinics in adjacent counties.'
  ),
  ALTER COLUMN nearest_statewide_safety_net_city SET OPTIONS (
    description = 'City (CMS_PROVIDER_CITY) of the nearest statewide safety-net clinic from care_sites_state.'
  ),
  ALTER COLUMN km_to_statewide_safety_net SET OPTIONS (
    description = 'Straight-line distance (km) from the tract centroid to the nearest safety-net clinic anywhere in the state (care_sites_state).'
  ),
  ALTER COLUMN cross_border_savings_km SET OPTIONS (
    description = 'Distance saved in kilometers (km_to_county_safety_net - km_to_statewide_safety_net) when a resident crosses the county boundary to visit a closer safety-net clinic in an adjacent county.'
  ),
  ALTER COLUMN acs_median_income SET OPTIONS (
    description = 'Median household income (USD) in the census tract from US Census ACS 5-year estimates (`bigquery-public-data.census_bureau_acs`).'
  ),
  ALTER COLUMN pct_poverty_acs SET OPTIONS (
    description = 'Percentage (%) of tract residents with income below the Federal Poverty Level from US Census ACS 5-year estimates.'
  ),
  ALTER COLUMN pct_black_acs SET OPTIONS (
    description = 'Percentage (%) of tract population identifying as Black or African American (non-Hispanic) from US Census ACS 5-year estimates. Reserved strictly for post-hoc equity auditing.'
  ),
  ALTER COLUMN pct_hispanic_acs SET OPTIONS (
    description = 'Percentage (%) of tract population identifying as Hispanic or Latino from US Census ACS 5-year estimates. Reserved strictly for post-hoc equity auditing.'
  ),
  ALTER COLUMN pct_white_acs SET OPTIONS (
    description = 'Percentage (%) of tract population identifying as White (non-Hispanic) from US Census ACS 5-year estimates. Reserved strictly for post-hoc equity auditing.'
  ),
  ALTER COLUMN pct_asian_acs SET OPTIONS (
    description = 'Percentage (%) of tract population identifying as Asian (non-Hispanic) from US Census ACS 5-year estimates. Reserved strictly for post-hoc equity auditing.'
  ),
  ALTER COLUMN pct_minority_acs SET OPTIONS (
    description = 'Percentage (%) of tract population identifying as any racial or ethnic minority (all persons except White non-Hispanic) from US Census ACS 5-year estimates. Reserved strictly for post-hoc equity auditing.'
  ),
  ALTER COLUMN svi_theme3_minority SET OPTIONS (
    description = 'CDC/ATSDR SVI 2022 Theme 3 (Racial & Ethnic Minority Status) national percentile rank (RPL_THEME3, 0.0 to 1.0). Excluded from burden_tracts and siting models; used exclusively in post-hoc equity auditing.'
  ),
  ALTER COLUMN svi_overall_with_theme3 SET OPTIONS (
    description = 'CDC/ATSDR SVI 2022 overall composite percentile rank across all four themes (RPL_THEMES, 0.0 to 1.0). Excluded from burden_tracts because it embeds Theme 3; used exclusively in post-hoc equity auditing.'
  ),
  ALTER COLUMN pct_minority_svi SET OPTIONS (
    description = 'Percentage (%) of tract population belonging to a racial or ethnic minority group from CDC/ATSDR SVI 2022 (EP_MINRTY). Reserved strictly for post-hoc equity auditing.'
  ),
  ALTER COLUMN pctile_minority_svi SET OPTIONS (
    description = 'National percentile rank (0.0 to 1.0) of minority population percentage from CDC/ATSDR SVI 2022 (EPL_MINRTY). Reserved strictly for post-hoc equity auditing.'
  ),
  ALTER COLUMN pct_black_svi SET OPTIONS (
    description = 'Percentage (%) of tract population identifying as Black or African American from CDC/ATSDR SVI 2022 (EP_AFAM). Reserved strictly for post-hoc equity auditing.'
  ),
  ALTER COLUMN pct_hispanic_svi SET OPTIONS (
    description = 'Percentage (%) of tract population identifying as Hispanic or Latino from CDC/ATSDR SVI 2022 (EP_HISP). Reserved strictly for post-hoc equity auditing.'
  ),
  ALTER COLUMN pct_asian_svi SET OPTIONS (
    description = 'Percentage (%) of tract population identifying as Asian from CDC/ATSDR SVI 2022 (EP_ASIAN). Reserved strictly for post-hoc equity auditing.'
  ),
  ALTER COLUMN pct_below_150pct_poverty_svi SET OPTIONS (
    description = 'Percentage (%) of tract persons with household income below 150% of the Federal Poverty Level from CDC/ATSDR SVI 2022 (EP_POV150).'
  ),
  ALTER COLUMN uninsured_ci_low SET OPTIONS (
    description = 'Lower bound of the 95% confidence interval for adult (18-64) uninsured prevalence (%) parsed from CDC PLACES access2_crup95ci.'
  ),
  ALTER COLUMN uninsured_ci_high SET OPTIONS (
    description = 'Upper bound of the 95% confidence interval for adult (18-64) uninsured prevalence (%) parsed from CDC PLACES access2_crup95ci.'
  ),
  ALTER COLUMN uninsured_ci_text SET OPTIONS (
    description = 'Formatted 95% confidence interval string (e.g., "(21.4, 28.9)") for adult uninsured prevalence from CDC PLACES access2_crup95ci.'
  ),
  ALTER COLUMN diabetes_ci_low SET OPTIONS (
    description = 'Lower bound of the 95% confidence interval for adult diagnosed diabetes prevalence (%) parsed from CDC PLACES diabetes_crup95ci.'
  ),
  ALTER COLUMN diabetes_ci_high SET OPTIONS (
    description = 'Upper bound of the 95% confidence interval for adult diagnosed diabetes prevalence (%) parsed from CDC PLACES diabetes_crup95ci.'
  ),
  ALTER COLUMN diabetes_ci_text SET OPTIONS (
    description = 'Formatted 95% confidence interval string for adult diagnosed diabetes prevalence from CDC PLACES diabetes_crup95ci.'
  ),
  ALTER COLUMN asthma_ci_low SET OPTIONS (
    description = 'Lower bound of the 95% confidence interval for adult current asthma prevalence (%) parsed from CDC PLACES casthma_crup95ci.'
  ),
  ALTER COLUMN asthma_ci_high SET OPTIONS (
    description = 'Upper bound of the 95% confidence interval for adult current asthma prevalence (%) parsed from CDC PLACES casthma_crup95ci.'
  ),
  ALTER COLUMN asthma_ci_text SET OPTIONS (
    description = 'Formatted 95% confidence interval string for adult current asthma prevalence from CDC PLACES casthma_crup95ci.'
  ),
  ALTER COLUMN copd_ci_low SET OPTIONS (
    description = 'Lower bound of the 95% confidence interval for adult COPD prevalence (%) parsed from CDC PLACES copd_crup95ci.'
  ),
  ALTER COLUMN copd_ci_high SET OPTIONS (
    description = 'Upper bound of the 95% confidence interval for adult COPD prevalence (%) parsed from CDC PLACES copd_crup95ci.'
  ),
  ALTER COLUMN copd_ci_text SET OPTIONS (
    description = 'Formatted 95% confidence interval string for adult COPD prevalence from CDC PLACES copd_crup95ci.'
  ),
  ALTER COLUMN high_bp_ci_low SET OPTIONS (
    description = 'Lower bound of the 95% confidence interval for adult high blood pressure prevalence (%) parsed from CDC PLACES bphigh_crup95ci.'
  ),
  ALTER COLUMN high_bp_ci_high SET OPTIONS (
    description = 'Upper bound of the 95% confidence interval for adult high blood pressure prevalence (%) parsed from CDC PLACES bphigh_crup95ci.'
  ),
  ALTER COLUMN high_bp_ci_text SET OPTIONS (
    description = 'Formatted 95% confidence interval string for adult high blood pressure prevalence from CDC PLACES bphigh_crup95ci.'
  ),
  ALTER COLUMN checkup_ci_low SET OPTIONS (
    description = 'Lower bound of the 95% confidence interval for adult routine checkup prevalence (%) parsed from CDC PLACES checkup_crup95ci.'
  ),
  ALTER COLUMN checkup_ci_high SET OPTIONS (
    description = 'Upper bound of the 95% confidence interval for adult routine checkup prevalence (%) parsed from CDC PLACES checkup_crup95ci.'
  ),
  ALTER COLUMN checkup_ci_text SET OPTIONS (
    description = 'Formatted 95% confidence interval string for adult routine checkup prevalence from CDC PLACES checkup_crup95ci.'
  ),
  ALTER COLUMN lack_transport_ci_low SET OPTIONS (
    description = 'Lower bound of the 95% confidence interval for adult lack of reliable transportation prevalence (%) parsed from CDC PLACES lacktrpt_crup95ci.'
  ),
  ALTER COLUMN lack_transport_ci_high SET OPTIONS (
    description = 'Upper bound of the 95% confidence interval for adult lack of reliable transportation prevalence (%) parsed from CDC PLACES lacktrpt_crup95ci.'
  ),
  ALTER COLUMN lack_transport_ci_text SET OPTIONS (
    description = 'Formatted 95% confidence interval string for adult lack of reliable transportation prevalence from CDC PLACES lacktrpt_crup95ci.'
  ),
  ALTER COLUMN corridor_name SET OPTIONS (
    description = 'Human-readable neighborhood or transit corridor name mapped to the census tract for community-facing explanations and mobile van dispatch.'
  ),
  ALTER COLUMN suggested_staging_landmark SET OPTIONS (
    description = 'Recommended real-world community staging landmark (e.g., transit station, library, recreation center, or shopping plaza) within or adjacent to the tract for parking a mobile health clinic.'
  ),
  ALTER COLUMN pct_minority SET OPTIONS (
    description = 'Harmonized percentage (%) of tract residents belonging to a racial or ethnic minority group (coalesced from SVI/ACS) for post-hoc equity auditing.'
  ),
  ALTER COLUMN pct_black SET OPTIONS (
    description = 'Harmonized percentage (%) of tract residents identifying as Black or African American (coalesced from SVI/ACS) for post-hoc equity auditing.'
  ),
  ALTER COLUMN pct_hispanic SET OPTIONS (
    description = 'Harmonized percentage (%) of tract residents identifying as Hispanic or Latino (coalesced from SVI/ACS) for post-hoc equity auditing.'
  ),
  ALTER COLUMN pct_asian SET OPTIONS (
    description = 'Harmonized percentage (%) of tract residents identifying as Asian (coalesced from SVI/ACS) for post-hoc equity auditing.'
  );


-- =============================================================================
-- 11. TABLE: field_reports
-- =============================================================================
ALTER TABLE `qwiklabs-gcp-04-f5825262a0a0.a4i_health.field_reports`
SET OPTIONS (
  description = 'Real-time community field reports logged by community health workers (CHWs), EMS/paramedics, and clinic coordinators (1 row per report). Captures ground-truth access barriers invisible to annual federal snapshots—such as temporary clinic closures, bus route cuts, shelter surges, or verified parking landmarks—and supplies an active severity_adjustment multiplier to update mobile clinic siting priorities.'
);

ALTER TABLE `qwiklabs-gcp-04-f5825262a0a0.a4i_health.field_reports`
  ALTER COLUMN report_id SET OPTIONS (
    description = 'Unique identifier for the structured community field report.'
  ),
  ALTER COLUMN reported_at SET OPTIONS (
    description = 'ISO-8601 timestamp or date string recording when the field report was submitted.'
  ),
  ALTER COLUMN geo_id SET OPTIONS (
    description = '11-character 2020 Census tract FIPS code (zero-padded STRING) to which the field report applies. Joins to burden_tracts.geo_id.'
  ),
  ALTER COLUMN reporter_role SET OPTIONS (
    description = 'Role of the frontline submitter (e.g., Community Health Worker, EMS/Paramedic, Outreach Coordinator, Clinic Navigator).'
  ),
  ALTER COLUMN barrier_type SET OPTIONS (
    description = 'Category of ground-truth access barrier or update (e.g., Clinic Closure/Reduced Hours, Transit Disruption, Unhoused Encampment/Shelter Surge, Language/Outreach Request, Verified Staging Site).'
  ),
  ALTER COLUMN severity_adjustment SET OPTIONS (
    description = 'Multiplicative priority adjustment factor (e.g., 1.0 = neutral, >1.0 = elevated urgency due to acute local barrier) applied to the tract siting score while active = TRUE.'
  ),
  ALTER COLUMN field_notes SET OPTIONS (
    description = 'Free-text qualitative observation from the field reporter describing local conditions, clinic waitlists, or community needs cited in the agent rationale.'
  ),
  ALTER COLUMN verified_landmark SET OPTIONS (
    description = 'Field-verified parking location or community landmark (with host permission/accessibility confirmed) for staging the mobile clinic van in the tract.'
  ),
  ALTER COLUMN active SET OPTIONS (
    description = 'Boolean flag (TRUE = currently active barrier/report; FALSE = resolved or superseded) controlling whether the report is included in live siting runs.'
  );
