ssc install power_tworates_zhu

program drop _all

local output_file "simulations.xlsx"


*/ Helper function to get % significant T1 error */
program count_values, rclass
    args var
    count if `var' <= 0.05 & `var' != -1 & `var' !=0
    scalar count = r(N)
    count if `var' ==. | `var' == -1 | `var' == 0
    scalar missing = r(N)
    scalar total = _N - missing
    matrix counts = round((100*count/total), 0.1), round(missing, 1)
    return matrix counts = counts
end

/* Make model names readable */
program rename_var, rclass
    args var
    di "`var'"
    local name_new = strproper("`var'")
    if strpos("`name_new'", "Dec") == 0 {
        local name_new = "`name_new' Manual Cuts"
    }
    local name_new = subinstr("`name_new'", "_Dec_", " Deciles ", 1)
    local name_new = subinstr("`name_new'", "_Dec", " Deciles ", 1)
    local name_new = subinstr("`name_new'", "_", " ", 1)
    return local name_new = "`name_new'"
end


/* For each year provided extract T1 error, dropped, and alpa into relevant matrix */
program generate_table, rclass
    args input_file year
    di "`input_file' `year'"
    use `input_file', clear
    summarize
    matrix J = ., .
    macro drop varnames
    // Base simulation models
    foreach var of varlist poisson poisson_dec zip zip_dec nb nb_dec zinb zinb_dec {
        count_values "`var'"
        matrix J = J \ r(counts)
        rename_var "`var'"
        di "`r(name_new)'"
        local varnames = `" `varnames' "`r(name_new)'" "'
    }
    matrix J = J \ .,.
    local varnames = `" `varnames' " - " "'
    // Outlier simulation models
    foreach var of varlist nb*_robbox* nb*_nbadjust* {
        count_values "`var'"
        matrix J = J \ r(counts)
        rename_var "`var'"
        di "`r(name_new)'"
        local varnames = `" `varnames' "`r(name_new)'" "'
    }
    matrix J = J[2..., 1...]
    matrix colnames J = "`year' Type 1 error %" "`year' Non-converging count"
    matrix rownames J = `varnames'
    return matrix vals = J

    matrix M = .,.
    local varnames ""
    // Overdispersion parameter
    foreach var of varlist alpha* {
        sum `var'
        scalar m = round(r(mean), 0.01)
        scalar sd = round(r(sd), 0.001)
        matrix M = M \ m,sd
        local varnames = "`varnames' `var'"
    }
    matrix M = M[2..., 1...]
    matrix colnames M = "`year' mean" "`year' sd"
    matrix rownames M = `varnames'
    return matrix overdispersion = M

    matrix L = .
    local varnames ""
    // Count of dropped variables
    foreach var of varlist dropped* {
        sum `var'
        scalar m = r(mean)
        matrix L = L \ m
        local varnames = "`varnames' `var'"
    }
    matrix L = L[2..., 1...]
    matrix colnames L = "`year'"
    matrix rownames L = `varnames'
    return matrix dropped = L
end


/* Find the highest irr for power above 0.9 to the nearest ten thousandth */
program get_irr, rclass
    args n2 overdispersion

    local irr_val = 0.95
    local power = 0
    while `power' < 0.9 {
        qui power tworates_zhu, n1(5000) n2("`n2'") irr("`irr_val'") r1(1.4) ///
            overdispersion("`overdispersion'")
        local power = r(power)
        local irr_val = `irr_val' - 0.0001
    }
    return scalar irr =  r(IRR)
end


/* For different settings of sample size and dispersion store highest irr */
program response_rate, rclass
    matrix column = .,.,.
    foreach j in 5000 3750 2500 1250 {
        matrix row = .
        local rownames = ""
        foreach i in 0.7 1.1 1.5 {
            get_irr `j' `i'
            matrix row = row , r(irr)
            local rownames = "`rownames' `i'"
        }
        matrix column = column \ row[1, 2...]
    }
    matrix column = column[2..., 1...]
    matrix rownames column = "Perfect" "Good" "Moderate" "Poor"
    matrix colnames column = `rownames'
    return matrix response_rate = column
end


/* Supplemental power table over various settings */
program power_supplemental, rclass
    power tworates_zhu, n1(4000 (500) 5000) r1(1.6) irr(0.88 (0.01) 0.94) ///
        overdispersion(1.0 (0.1) 1.6)
    matrix power = r(pss_table)
    matrix one = power[1...,2..3]
    matrix two = power[1...,6..8]
    matrix three = power[1...,10]
    matrix power_filtered = one, two, three
    return matrix power_sup = power_filtered
end


/* Extract data for 3 years */
generate_table "data_latest/2018_10000_years.dta" "2018"
matrix A = r(vals)
matrix A_dropped = r(dropped)
matrix A_overdispersion = r(overdispersion)
generate_table "data_latest/2019_10000_years.dta" "2019"
matrix B = r(vals)
matrix B_dropped = r(dropped)
matrix B_overdispersion = r(overdispersion)
generate_table "data_latest/2020_10000_years.dta" "2020"
matrix C = r(vals)
matrix C_dropped = r(dropped)
matrix C_overdispersion = r(overdispersion)

matrix out = A, B, C
matrix out_dropped = A_dropped, B_dropped, C_dropped
matrix out_overdispersion = A_overdispersion, ///
    B_overdispersion, C_overdispersion

putexcel set "`output_file'", sheet("error_rate") replace
putexcel A1=matrix(out), names

putexcel set "`output_file'", sheet("dropped") modify
putexcel A1=matrix(out_dropped), names nformat(number)

putexcel set "`output_file'", sheet("overdispersion") modify
putexcel A1=matrix(out_overdispersion), names

response_rate
putexcel set "`output_file'", sheet("response_rate") modify
putexcel (B1:D1)="Overdispersion parameter", merge hcenter
putexcel A2=matrix(r(response_rate)), names nformat(number_d2)
putexcel A2="Intervention condition"


power_supplemental
putexcel set "`output_file'", sheet("power") modify
putexcel A1=matrix(r(power_sup)), colnames nformat(number_d2)
