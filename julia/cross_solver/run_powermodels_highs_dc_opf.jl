using HiGHS
using JuMP
using PowerModels

if length(ARGS) != 2
    error("usage: run_powermodels_highs_dc_opf.jl INPUT_TSV OUTPUT_TSV")
end

PowerModels.silence()
input_path, output_path = ARGS
optimizer = JuMP.optimizer_with_attributes(HiGHS.Optimizer, "output_flag" => false)

open(output_path, "w") do output
    println(output, join([
        "network", "scale", "termination_status", "objective", "total_generation_mw",
        "solve_time_s", "julia_version", "powermodels_version", "highs_version"
    ], '\t'))
    for line in eachline(input_path)
        isempty(strip(line)) && continue
        fields = split(line, '\t')
        length(fields) == 3 || error("invalid input row: $line")
        network, path, scale_text = String.(fields)
        scale = parse(Float64, scale_text)
        data = PowerModels.parse_file(path)
        for load in values(data["load"])
            load["pd"] *= scale
            load["qd"] *= scale
        end
        result = PowerModels.solve_dc_opf(data, optimizer)
        objective = get(result, "objective", NaN)
        solve_time = get(result, "solve_time", NaN)
        base_mva = data["baseMVA"]
        total_generation = base_mva * sum(
            get(generator, "pg", 0.0)
            for generator in values(get(result["solution"], "gen", Dict()))
        )
        println(output, join([
            network,
            string(scale),
            string(result["termination_status"]),
            string(objective),
            string(total_generation),
            string(solve_time),
            string(VERSION),
            string(Base.pkgversion(PowerModels)),
            string(Base.pkgversion(HiGHS)),
        ], '\t'))
    end
end
