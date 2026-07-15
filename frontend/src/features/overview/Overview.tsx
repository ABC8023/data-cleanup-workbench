import type { DatasetProfile } from '../../api/types'

interface OverviewProps {
  profile: DatasetProfile
  findingCount: number
}

export function Overview({ profile, findingCount }: OverviewProps) {
  return (
    <section aria-labelledby="overview-heading">
      <h2 id="overview-heading">Overview</h2>
      <p>
        {profile.row_count.toLocaleString()} rows · {profile.columns.length}{' '}
        columns · {findingCount} findings
      </p>
      <table>
        <caption>Column profile</caption>
        <thead>
          <tr>
            <th scope="col">Column</th>
            <th scope="col">Type</th>
            <th scope="col">Nulls</th>
            <th scope="col">Distinct</th>
            <th scope="col">Examples</th>
          </tr>
        </thead>
        <tbody>
          {profile.columns.map((column) => (
            <tr key={column.name}>
              <th scope="row">{column.name}</th>
              <td>{column.inferred_type}</td>
              <td>{column.null_count.toLocaleString()}</td>
              <td>{column.distinct_count.toLocaleString()}</td>
              <td>
                <details>
                  <summary>Show samples</summary>
                  {column.examples.join(', ')}
                </details>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  )
}
