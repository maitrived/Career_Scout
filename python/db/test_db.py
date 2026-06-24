import os
from python.db.client import get_connection, save_job, get_job, get_unscored_jobs, save_score, save_resume_version, save_application, get_ready_applications, get_pipeline_status
from python.db.models import Job, Score, ResumeVersion, Application

def test_sqlite_db():
    print("====================================================")
    print("Testing local SQLite DB client and Pydantic integration")
    print("====================================================")
    
    # 1. Clean up any existing test data to ensure clean run
    conn = get_connection()
    conn.execute("DELETE FROM jobs WHERE external_id = 'test_dummy_id_12345'")
    conn.commit()
    conn.close()

    # 2. Save a new Job
    dummy_job = Job(
        source="greenhouse",
        external_id="test_dummy_id_12345",
        company="Vybd Test Room",
        title="Software Engineer (Test)",
        location="Scottsdale, AZ",
        remote=True,
        url="https://example.com/test-job-url",
        raw_jd="This is a test job description for the Auto-Applier pipeline. Requires Python, FastAPI, and PostgreSQL."
    )

    print("\n1. Instantiating and saving Job model...")
    saved_job = save_job(dummy_job)
    print(f"[SUCCESS] Job saved with internal ID: {saved_job.id}")

    # 3. Retrieve Job
    print("\n2. Retrieving Job from DB...")
    retrieved_job = get_job(str(saved_job.id))
    if retrieved_job and str(retrieved_job.id) == str(saved_job.id):
        print(f"[SUCCESS] Retrieved correct job: '{retrieved_job.company}' - '{retrieved_job.title}'")
    else:
        print("[ERROR] Job retrieval failed or returned incorrect data!")
        return

    # 4. Check Unscored Jobs list
    print("\n3. Testing get_unscored_jobs...")
    unscored = get_unscored_jobs()
    unscored_ids = [str(j.id) for j in unscored]
    if str(saved_job.id) in unscored_ids:
        print(f"[SUCCESS] Dummy job correctly identified as unscored (Total unscored: {len(unscored)})")
    else:
        print("[ERROR] Dummy job missing from unscored list!")
        return

    # 5. Save a Score
    print("\n4. Saving Score for Job...")
    dummy_score = Score(
        job_id=saved_job.id,
        embedding_similarity=0.82,
        overall_score=4.5,
        tech_fit=4.8,
        level_fit=4.0,
        growth_signal=4.0,
        culture_signal=4.5,
        rationale="Excellent alignment with Vybd and Orbit supply chain stack. Python and PostgreSQL matches.",
        red_flags=["None"]
    )
    saved_score = save_score(dummy_score)
    print(f"[SUCCESS] Score saved successfully (ID: {saved_score.id})")

    # 6. Verify Unscored list again (should be gone now)
    print("\n5. Verifying job is no longer listed in unscored...")
    unscored_after = get_unscored_jobs()
    unscored_after_ids = [str(j.id) for j in unscored_after]
    if str(saved_job.id) not in unscored_after_ids:
        print("[SUCCESS] Job correctly moved out of unscored list!")
    else:
        print("[ERROR] Job is still showing up as unscored after being scored!")
        return

    # 7. Save a ResumeVersion
    print("\n6. Saving Tailored Resume Version...")
    dummy_rv = ResumeVersion(
        job_id=saved_job.id,
        resume_md="# Parva - Tailored Resume\nSome tailored bullets...",
        cover_letter="Dear Hiring Manager,\nI am writing to express my interest...",
        pdf_path=f"output/{saved_job.id}.pdf"
    )
    saved_rv = save_resume_version(dummy_rv)
    print(f"[SUCCESS] ResumeVersion saved successfully (ID: {saved_rv.id})")

    # 8. Save an Application
    print("\n7. Saving Application tracker...")
    dummy_app = Application(
        job_id=saved_job.id,
        resume_version_id=saved_rv.id,
        status="ready"
    )
    saved_app = save_application(dummy_app)
    print(f"[SUCCESS] Application saved successfully (ID: {saved_app.id}, Status: {saved_app.status})")

    # 9. Get Ready Applications and pipeline status
    print("\n8. Checking ready applications list...")
    ready_apps = get_ready_applications()
    ready_job_ids = [str(a['job_id']) for a in ready_apps]
    if str(saved_job.id) in ready_job_ids:
        print(f"[SUCCESS] Correctly fetched ready application package! Count: {len(ready_apps)}")
    else:
        print("[ERROR] App not listed in get_ready_applications!")
        return

    print("\n9. Testing get_pipeline_status...")
    status = get_pipeline_status()
    print(f"[SUCCESS] Pipeline Status Dashboard Metrics: {status}")

    # 10. Clean up
    print("\n10. Cleaning up test data...")
    conn = get_connection()
    conn.execute("DELETE FROM jobs WHERE id = ?", (str(saved_job.id),))
    conn.commit()
    conn.close()
    print("[SUCCESS] Cleanup finished! Local SQLite DB is completely functional.")
    print("====================================================")


