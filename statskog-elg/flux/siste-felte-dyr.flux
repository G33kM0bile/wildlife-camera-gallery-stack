from(bucket: "Wildlife")
  |> range(start: 2019-01-01T00:00:00Z, stop: now())
  |> filter(fn: (r) =>
    r._measurement == "elg_felling" and
    r.jaktfelt_id == "1840J0096" and
    contains(value: r._field, set: ["felling", "kategori", "kategori_skutt", "slaktevekt"])
  )
  |> pivot(rowKey: ["_time", "storvilt_id"], columnKey: ["_field"], valueColumn: "_value")
  |> group()
  |> sort(columns: ["_time"], desc: true)
  |> limit(n: 20)
  |> keep(columns: ["_time", "storvilt_id", "kategori", "kategori_skutt", "slaktevekt"])
  |> yield(name: "siste_felte_dyr")
