import "date"

base = from(bucket: "Wildlife")
  |> range(start: date.truncate(t: now(), unit: 1y), stop: now())
  |> filter(fn: (r) =>
    r._measurement == "elg_felling" and
    r.jaktfelt_id == "1840J0096" and
    (r._field == "felling" or r._field == "jaktlag")
  )
  |> pivot(
    rowKey: ["_time", "storvilt_id"],
    columnKey: ["_field"],
    valueColumn: "_value",
  )
  |> map(fn: (r) => ({r with jaktlag: if exists r.jaktlag then r.jaktlag else "Andre"}))

jaktlag1 = base
  |> filter(fn: (r) => r.jaktlag == "Jaktlag 1")
  |> keep(columns: ["_time", "felling"])
  |> group()
  |> sort(columns: ["_time"])
  |> cumulativeSum(columns: ["felling"])
  |> rename(columns: {felling: "Jaktlag 1"})

jaktlag2 = base
  |> filter(fn: (r) => r.jaktlag == "Jaktlag 2")
  |> keep(columns: ["_time", "felling"])
  |> group()
  |> sort(columns: ["_time"])
  |> cumulativeSum(columns: ["felling"])
  |> rename(columns: {felling: "Jaktlag 2"})

andre = base
  |> filter(fn: (r) => r.jaktlag == "Andre")
  |> keep(columns: ["_time", "felling"])
  |> group()
  |> sort(columns: ["_time"])
  |> cumulativeSum(columns: ["felling"])
  |> rename(columns: {felling: "Andre"})

union(tables: [jaktlag1, jaktlag2, andre])
  |> yield(name: "Fellinger per jaktlag")
