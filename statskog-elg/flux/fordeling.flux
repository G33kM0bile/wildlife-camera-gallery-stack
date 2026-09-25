from(bucket: "Wildlife")
  |> range(start: 2019-01-01T00:00:00Z, stop: now())
  |> filter(fn: (r) =>
    r._measurement == "elg_felling" and
    r.jaktfelt_id == "1840J0096" and
    contains(value: r._field, set: ["felling", "kategori_skutt"])
  )
  |> pivot(rowKey: ["_time", "storvilt_id"], columnKey: ["_field"], valueColumn: "_value")
  |> group(columns: ["kategori_skutt"])
  |> sum(column: "felling")
  |> keep(columns: ["kategori_skutt", "felling"])
  |> rename(columns: {felling: "antall"})
  |> group()
  |> yield(name: "fordeling")
