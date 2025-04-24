# Odoo Operator Database Management Revamp

## Background

The current Odoo Kubernetes operator manages Odoo instances but has limited functionality for database management, particularly around restorations. The existing implementation relies on Odoo's built-in database manager interface, which can lead to naming conflicts and lacks the automation needed for efficient environment management (e.g., creating staging environments from production backups).

## Objectives

1. **Operator-Controlled Database Naming**
   - Implement a deterministic naming scheme for databases managed by the operator
   - Disable Odoo's built-in database manager interface
   - Prevent naming conflicts between different environments

2. **Restoration Capabilities**
   - Enable restoration of production databases from existing S3 backups
   - Facilitate creation of staging environments from production backups
   - Support specifying the source backup S3 location when creating/restoring an instance
   - Implement data sanitization for non-production environments (optional)

3. **Instance Relationship Management**
   - Define and maintain relationships between production and non-production instances
   - Track the source production instance for each staging instance
   - Enable easy identification of related instances across environments
   - Support operations that leverage these relationships (e.g., "reload this staging from its production")

4. **Kubernetes Integration**
   - Leverage Kubernetes Custom Resources for defining restore operations
   - Implement status reporting for restore operations
   - Integrate with Kubernetes events for operation logging

## Implementation Considerations

### Database Naming Strategy

- Format: `{first-fqdn-from-instance-config}-{uuid-suffix}`
- Example: `erp.example.com-a1b2c3d4`
- Benefits: 
  - Provides a recognizable name based on the instance's domain
  - UUID suffix ensures uniqueness and prevents conflicts
  - Eliminates the need for manual database naming
  - Makes it easy to identify which instance a database belongs to

### Instance Relationship Model

- Extend the CRD to include relationship metadata
- Example fields:
  - `instanceType`: "production" | "staging" | "development"
  - `relatedTo`: Reference to the production instance (for non-production instances)
  - `lastRestoredFrom`: S3 location of the backup used for the last restore
  - `lastRestoreTime`: Timestamp of the last restoration

### Backup Source Configuration

- Support for S3 as the primary backup source
- Required configuration:
  - S3 bucket and path
  - AWS credentials/IAM role
  - Backup file format (e.g., SQL dump, compressed archive)
- Optional metadata about available backups

### Restoration Process

#### For Production Instances (from S3 backup)
1. Create a backup of the target instance (if it exists and if requested)
2. Download the source backup from S3
3. Restore the database
4. Update relationship metadata
5. Restart the Odoo instance

#### For Production Instances (from existing database)
1. Create a backup of the target instance (if it exists and if requested)
2. Make a copy of the specified existing database in the PostgreSQL server
   - Create a new database with the instance's generated name
   - Copy all data from the source database to the new database
   - Assign the database to the instance's user with appropriate permissions
3. Update relationship metadata
4. Restart the Odoo instance

#### For Staging Instances (from Production)
1. Make a copy of the database in the database server
   - Create a new database with the staging instance's generated name
   - Copy all data from the production database to the staging database
   - Assign the database to the staging instance's user with appropriate permissions
2. Make a copy of the Kubernetes Odoo data volume from the production server
   - Use volume snapshots or other appropriate Kubernetes volume operations
   - Ensure all filestore data is properly copied
   - Rename the filestore folder appropriately to match the new DB name
3. Run odoo's neutralization functionality in an init container
4. Update relationship metadata to track the connection to the production instance
5. Restart the Odoo instance

### Handling Restoration to Running Production Servers

When restoring a database to a running production server, special considerations are needed to ensure minimal disruption and maintain data integrity:

1. **Parallel Database and Filestore Approach**
   - Rather than immediately replacing the existing database and filestore, the operator will:
     - Restore the database to a new database name
     - Restore the filestore to a new PVC
     - Update the Odoo configuration to use the new database (via the `dbfilter` parameter)
     - Point to the new filestore PVC

2. **Transition Process**
   - The operator will:
     - Perform the restoration to new resources (new database and new PVC)
     - Update the Odoo configuration to use the new database and filestore
     - Restart the Odoo instance to use the new database and filestore
     - Keep the old database and filestore intact for a defined period

3. **Cleanup**
   - After a configurable retention period (default: 7 days):
     - The old database will be dropped
     - The old filestore PVC will be deleted
   - This allows for quick rollback if issues are discovered with the restored data

4. **Resource Tracking**
   - The operator will maintain metadata about current and previous resources in the OdooInstance status:
     ```yaml
     status:
       storage:
         current:
           database: "example.com-a1b2c3d4"
           filestore: "odoo-data-example-a1b2c3d4"
           createdAt: "2025-04-24T10:30:00Z"
         previous:
           - database: "example.com-e5f6g7h8"
             filestore: "odoo-data-example-e5f6g7h8"
             createdAt: "2025-03-15T08:45:00Z"
             scheduledForDeletionAt: "2025-05-01T10:30:00Z"
           - database: "example.com-i9j0k1l2"
             filestore: "odoo-data-example-i9j0k1l2"
             createdAt: "2025-02-10T14:20:00Z"
             scheduledForDeletionAt: "2025-04-15T08:45:00Z"
     ```
   - This metadata enables:
     - Easy identification of current and previous storage resources
     - Tracking of when resources were created and when they're scheduled for deletion
     - Simple rollback to any previous version by selecting from the list
     - Maintaining a history of database changes over time
     - Ensuring database and filestore pairs remain synchronized

5. **Rollback Mechanism**
   - If issues are discovered with the restored database:
     - The operator can quickly revert to any previous storage configuration using the stored metadata
     - This is done by updating the Odoo configuration to point back to the selected previous resources
     - The rollback command would specify which previous version to restore to
     - No data restoration is needed, minimizing downtime

This approach provides several advantages:
- Minimizes risk when restoring to production environments
- Provides a quick rollback mechanism if issues are discovered
- Avoids the need to immediately delete potentially valuable data
- Allows for verification of the restored data before committing to it fully

### Security Considerations

- Implement role-based access control for database operations
- Ensure secure handling of S3 credentials
- Sanitize sensitive information when creating non-production environments

## Next Steps

1. Define the CRD extensions needed for restore operations and instance relationships
2. Implement the database naming strategy
3. Develop the S3 backup retrieval functionality
4. Implement the restoration process
5. Create documentation and examples
6. Test in development environments before rolling out to production

## Additional Implementation Details

### Error Handling and Recovery

- Implement robust error handling for each step of the restoration process
- Create recovery mechanisms for partially completed operations
- Provide clear error messages and logging for troubleshooting
- Consider implementing a rollback mechanism for failed restorations

### Monitoring and Observability

- Create Kubernetes events for significant state changes in the restoration process
- Implement detailed logging for each step of database operations
- Update the instance status with clear information about ongoing and completed operations
- Ensure error messages are descriptive and actionable

### CRD Design Considerations

#### OdooInstance CRD Extensions
```yaml
apiVersion: bemade.io/v1
kind: OdooInstance
metadata:
  name: example-instance
spec:
  # Existing fields...
  
  # New fields for database management
  database:
    # Optional: specify a specific name override (otherwise generated from FQDN)
    nameOverride: ""
    
    # For staging instances
    stagingConfig:
      # Reference to the production instance this is a staging for
      productionInstanceRef: "production-instance"
  
status:
  # Existing fields...
  
  # New fields for database status
  database:
    name: "example.com-a1b2c3d4"
    lastRestoreTime: "2025-04-23T14:30:00Z"
    lastRestoreSource: "production-instance" # or S3 location
    restoreStatus: "Completed" # In Progress, Failed, Completed
    restoreMessage: ""
```

#### New Custom Resources

```yaml
# For restoring from S3 backups
apiVersion: bemade.io/v1
kind: OdooInstanceRestore
metadata:
  name: restore-production-from-s3
spec:
  # Target instance to restore
  targetInstance: "production-instance"
  
  # S3 source configuration
  source:
    type: "s3"
    s3:
      bucketName: "odoo-backups"
      objectKey: "production/backup-20250423.dump"
      secretRef:
        name: "s3-credentials"
  
  # Optional: schedule for future execution
  scheduledTime: "2025-04-24T22:00:00Z"
  
status:
  phase: "Scheduled" # Pending, In Progress, Completed, Failed
  message: ""
  startTime: ""
  completionTime: ""
```

```yaml
# For restoring from an existing database
apiVersion: bemade.io/v1
kind: OdooInstanceRestore
metadata:
  name: restore-from-existing-db
spec:
  # Target instance to restore
  targetInstance: "production-instance"
  
  # Existing database source configuration
  source:
    type: "existingDatabase"
    existingDatabase:
      name: "legacy_database_name"
      # Optional: if the database is on a different PostgreSQL server
      host: "external-postgres.example.com"
      port: 5432
      secretRef:
        name: "external-db-credentials"
  
status:
  phase: "Pending" # Pending, In Progress, Completed, Failed
  message: ""
  startTime: ""
  completionTime: ""
```

```yaml
# For reloading a staging instance from its production instance
apiVersion: bemade.io/v1
kind: OdooInstanceReload
metadata:
  name: reload-staging-2025-04-24
spec:
  # Staging instance to reload
  stagingInstance: "staging-instance"
  # Optional: schedule for future execution
  scheduledTime: "2025-04-24T22:00:00Z"
status:
  phase: "Scheduled" # Pending, In Progress, Completed, Failed
  message: ""
  startTime: ""
  completionTime: ""
```

### Neutralization Process

The neutralization init container should:

1. Connect to the newly created database
2. Execute standard Odoo neutralization operations:
   - Disable outgoing emails or redirect to internal addresses
   - Reset or anonymize sensitive customer data if required
   - Disable scheduled actions that might affect production systems
   - Add visual indicators in the UI that this is a staging environment
3. Add a system parameter indicating this is a staging environment

This can be implemented using Odoo's shell command with a Python script or by using Odoo's API.

## Implementation Decisions

### Migration of Existing Databases

- Existing databases will be migrated by providing a database name to copy from in the OdooInstance CRD
- This will be specified in the Odoo operator helm values or through an OdooInstanceRestore with source type "existingDatabase"
- The operator will handle copying the data and setting up the new database with the generated name
- This approach supports both databases on the same PostgreSQL server and external databases

### Staging Environment Creation

- Initially, staging environments will be created manually by creating an OdooInstance either as YAML or from the helm chart
- In the future, this will be managed through an Odoo module with a web UI
- The relationship to the production instance will be specified in the stagingConfig

### Handling Restoration Failures

- For new instances, restoration failures don't require special handling as there's no existing state to preserve
- For existing instances:
  - The operator will keep track of the previous database name in metadata
  - Restoration will be performed on a new database name
  - The instance will only be switched to the new database if restoration is successful
  - If restoration fails, the instance will continue using its old database
  - This approach provides a safe rollback mechanism

### Concurrency and Parallelism

- Multiple read operations (e.g., creating multiple staging instances from a single production) can run in parallel
- Only one restore job can run for a specific instance at a time
- No explicit parallelism controls are needed for general database operations
- The operator will implement appropriate locking mechanisms to prevent conflicting operations

### Database Credentials Management

- Database credentials are already managed for OdooInstances through the Kubernetes operator
- No additional credential management is needed across non-Kubernetes environments
- The operator will continue to use the existing credential management system

### Production-Staging Relationships

- Production-staging relationships are fixed and cannot be changed after creation
- If a different relationship is needed, a new staging instance must be created

## Additional Implementation Considerations

### Database Restoration Status Tracking

- The operator will track the restoration status of each database in the OdooInstance status
- A new field `initialRestorationComplete` will be added to indicate whether the initial database setup has been completed
- For new instances:
  - When an OdooInstance is first created, `initialRestorationComplete` is set to `false`
  - After successful restoration (either from S3 or from a production instance), it's set to `true`
  - The operator will automatically trigger the appropriate restoration process for instances with `initialRestorationComplete: false`
- For existing instances being migrated:
  - When providing a database name to copy from, `initialRestorationComplete` is set to `true` after the migration
  - This indicates that no further initial restoration is needed
- For reload operations:
  - These are explicit user-triggered actions and don't affect the `initialRestorationComplete` status
  - The reload status is tracked separately in the OdooInstanceReload resource

This approach allows the operator to:
1. Automatically identify instances that still need initial database setup
2. Distinguish between initial setup and subsequent reload operations
3. Provide clear status information about the database state
4. Handle migration scenarios appropriately

#### Status Example

```yaml
status:
  # Existing fields...
  
  # Database status fields
  database:
    name: "example.com-a1b2c3d4"
    initialRestorationComplete: true
    lastRestoreTime: "2025-04-23T14:30:00Z"
    lastRestoreSource: "production-instance" # or S3 location
    restoreStatus: "Completed" # In Progress, Failed, Completed
    restoreMessage: ""
```

### Staging Environment Lifecycle

- **Creation**: When a staging OdooInstance is created with a productionInstanceRef, it automatically gets populated with data from the production instance
- **Usage**: Staging environments are used for testing, development, and demonstration purposes
- **Reload**: When a staging environment needs fresh data, a complete reload is performed rather than an incremental update
- **Deletion**: Staging environments can be deleted and recreated as needed without affecting other environments

### Reload Operation

The reload operation recreates a staging environment with fresh data from its production instance:

1. The operator preserves the staging instance's configuration
2. The existing staging instance is deleted (including database and filestore)
3. A new staging instance is created with the same configuration
4. The standard process for creating a staging instance from production is followed

This disposable approach to staging environments offers several advantages:
- Ensures staging always starts from a known, clean state
- Eliminates potential issues from accumulated changes in staging
- Simplifies the implementation by avoiding incremental update logic
- Provides consistent behavior for testing and development
