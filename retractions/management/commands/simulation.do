/*
ssc install robstat
ssc install moremata
ssc install robbox
ssc install nb_adjust
*/

sysdir set PLUS data_latest/stata_libs
set maxvar 30000, permanently

local input_file "`1'"
local output_file "`2'"
local subset "`3'"

program drop _all

program model_sim_strata, rclass
    args subset

    local groups = "trt_groups_" + "`=i'"
    local trt_groups = "`groups'_factor"
    local deciles = "trt_deciles_" + "`=i'"
    local trt_deciles = "`deciles'_factor"

    di "`=i'"
    di "`trt_groups'"
    di "`trt_deciles'"
    encode `groups', gen(`trt_groups')
    encode `deciles', gen(`trt_deciles')


    if "`subset'"!="true" {
        // Run poisson
        poisson citation_count i.`trt_groups' i.groups, iterate(200)
        matrix res = r(table)
        if e(converged) {
            return scalar poisson_p = res[4, 2]
        }
        else {
            return scalar poisson_p = -1
        }

        // Run zip
        zip citation_count i.`trt_groups' i.groups, ///
            inflate(i.`trt_groups' i.groups i.years_since_retraction_q4) iterate(200)
        matrix res = r(table)
        return scalar zip_p = res[4, 2]

        // Run nb
        nbreg citation_count i.`trt_groups' i.groups, nolrtest
        matrix res = r(table)
        return scalar nb_p = res[4, 2]

        // Run zinb
        zinb citation_count i.`trt_groups' i.groups, ///
            inflate(i.`trt_groups' i.groups i.years_since_retraction_q4) iterate(200)
        matrix res = r(table)
        if e(converged) {
            return scalar zinb_p = res[4, 2]
        }
        else {
            return scalar zinb_p = -1
        }

        /* Use deciles instead */
        // Run poisson
        poisson citation_count i.`trt_deciles' i.deciles, iterate(200)
        matrix res = r(table)
        if e(converged) {
            return scalar poisson_p_dec = res[4, 2]
        }
        else {
            return scalar poisson_p_dec = -1
        }

        // Run zip
        zip citation_count i.`trt_deciles' i.deciles, ///
            inflate(`trt_deciles' i.deciles i.years_since_retraction_q4) iterate(200)
        matrix res = r(table)
        return scalar zip_p_dec = res[4, 2]

        // Run nb
        nbreg citation_count i.`trt_deciles' i.deciles, nolrtest
        matrix res = r(table)
        return scalar nb_p_dec = res[4, 2]
        return scalar alpha = e(alpha)

        // Run zinb
        zinb citation_count i.`trt_deciles' i.deciles, ///
            inflate(`trt_deciles' i.deciles i.years_since_retraction_q4) iterate(200)
        matrix res = r(table)
        if e(converged) {
            return scalar zinb_p_dec = res[4, 2]
        }
        else {
            return scalar zinb_p_dec = -1
        }

    }

    /* Drop outliers with robbox*/
    robbox citation_count, adjusted nograph
    matrix whiskers = e(whiskers)
    scalar max = whiskers[2, 1]
    matrix dropped = e(N_out)
    return scalar dropped_robbox = dropped[2, 1]
    //drop if citation_count > max
    gen citation_robbox = citation_count
    replace citation_robbox = . if citation_count > max

    // Run nb
    nbreg citation_robbox i.`trt_groups' i.groups, nolrtest
    matrix res = r(table)
    return scalar alpha_robbox = e(alpha)
    if e(converged) {
        return scalar nb_p_robbox = res[4, 2]
    }
    else {
        return scalar nb_p_robbox = -1
    }

    // Run nb deciles
    nbreg citation_robbox i.`trt_deciles' i.deciles, nolrtest
    matrix res = r(table)
    if e(converged) {
        return scalar nb_p_dec_robbox = res[4, 2]
    }
    else {
        return scalar nb_p_dec_robbox = -1
    }

    nb_adjust citation_count, rem g(citation_nb_adjust)
    return scalar dropped_nbadjust = r(nout)
    //drop if citation_count != adjusted

    // Run nb
    nbreg citation_nb_adjust i.`trt_groups' i.groups, nolrtest
    matrix res = r(table)
    return scalar alpha_nbadjust = e(alpha)
    if e(converged) {
        return scalar nb_p_nbadjust = res[4, 2]
    }
    else {
        return scalar nb_p_nbadjust = -1
    }

    // Run nb deciles
    nbreg citation_nb_adjust i.`trt_deciles' i.deciles, nolrtest
    matrix res = r(table)
    if e(converged) {
        return scalar nb_p_dec_nbadjust = res[4, 2]
    }
    else {
        return scalar nb_p_dec_nbadjust =  -1
    }


    /* Robust */
    // Run nb
    nbreg citation_nb_adjust i.`trt_groups' i.groups, nolrtest robust
    matrix res = r(table)
    if e(converged) {
        return scalar nb_p_nbadjust_robust = res[4, 2]
    }
    else {
        return scalar nb_p_nbadjust_robust = -1
    }

    // Run nb deciles robust
    nbreg citation_nb_adjust i.`trt_deciles' i.deciles, nolrtest robust
    matrix res = r(table)
    if e(converged) {
        return scalar nb_p_dec_nbadjust_robust = res[4, 2]
    }
    else {
        return scalar nb_p_dec_nbadjust_robust = -1
    }

    // Cleanup temp vars
    drop `trt_groups'
    drop `trt_deciles'
    drop citation_robbox
    drop citation_nb_adjust


    return scalar index = i
    scalar i = scalar(i) + 1

end

insheet using `input_file', clear

scalar i = 0
simulate index=r(index) dropped_robbox=r(dropped_robbox) dropped_nbadjust=r(dropped_nbadjust) ///
    alpha=r(alpha) alpha_robbox=r(alpha_robbox) alpha_nbadjust=r(alpha_nbadjust) ///
    poisson=r(poisson_p) zip=r(zip_p) nb=r(nb_p) zinb=r(zinb_p) ///
    poisson_dec=r(poisson_p_dec) zip_dec=r(zip_p_dec) nb_dec=r(nb_p_dec) zinb_dec=r(zinb_p_dec) ///
    nb_robbox=r(nb_p_robbox) nb_dec_robbox=r(nb_p_dec_robbox) nb_nbadjust=r(nb_p_nbadjust) ///
    nb_dec_nbadjust=r(nb_p_dec_nbadjust) nb_nbadjust_robust=r(nb_p_nbadjust_robust) ///
    nb_dec_nbadjust_robust=r(nb_p_dec_nbadjust_robust), reps(500) seed(1234) verbose ///
    saving("`output_file'", replace every(100)): model_sim_strata "`subset'"
