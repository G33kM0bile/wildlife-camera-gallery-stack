from(bucket: "Wildlife")
  |> range(start: 2019-01-01T00:00:00Z, stop: now())
  |> filter(fn: (r) =>
    r._measurement == "elg_felling" and
    r.jaktfelt_id == "1840J0096" and
    r._field == "slaktevekt"
  )
  |> mean()
  |> yield(name: "gjennomsnittlig_slaktevekt")
