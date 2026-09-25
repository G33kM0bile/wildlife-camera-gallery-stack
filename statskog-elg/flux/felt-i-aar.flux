import "date"

from(bucket: "Wildlife")
  |> range(start: date.truncate(t: now(), unit: 1y), stop: now())
  |> filter(fn: (r) =>
    r._measurement == "elg_felling" and
    r.jaktfelt_id == "1840J0096" and
    r._field == "felling"
  )
  |> sum()
  |> yield(name: "felt_i_aar")
