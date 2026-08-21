// The stripped-back version: exactly the six stages the lab asks for, with
// nothing extra. Compare it against the main Jenkinsfile — the difference
// between the two files is the complete list of optional additions.
//
// To use this instead: rename it to `Jenkinsfile`, or set the job's
// "Script Path" to Jenkinsfile.minimal.
//
// Before running, edit the two CHANGE_ME values below.

pipeline {
    agent any

    environment {
        IMAGE_NAME = 'CHANGE_ME/weather-app'   // your Docker Hub username
        APP_HOST   = 'CHANGE_ME'               // terraform output -raw app_private_ip
        IMAGE_TAG  = "${env.BUILD_NUMBER}"
    }

    stages {

        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Install / Build') {
            steps {
                sh '''
                    set -eu
                    python3 -m venv .venv
                    . .venv/bin/activate
                    pip install -r app/requirements.txt -r app/requirements-dev.txt
                '''
            }
        }

        stage('Test') {
            steps {
                sh '''
                    set -eu
                    . .venv/bin/activate
                    pytest --junitxml=test-results.xml
                '''
            }
            post {
                always {
                    junit 'test-results.xml'
                }
            }
        }

        stage('Docker Build') {
            steps {
                sh 'docker build --build-arg APP_VERSION="${IMAGE_TAG}" -t "${IMAGE_NAME}:${IMAGE_TAG}" app/'
            }
        }

        stage('Push Image') {
            steps {
                withCredentials([usernamePassword(
                    credentialsId: 'registry_creds',
                    usernameVariable: 'REGISTRY_USER',
                    passwordVariable: 'REGISTRY_PASS'
                )]) {
                    sh '''
                        set -eu
                        echo "${REGISTRY_PASS}" | docker login -u "${REGISTRY_USER}" --password-stdin
                        docker push "${IMAGE_NAME}:${IMAGE_TAG}"
                    '''
                }
            }
        }

        stage('Deploy') {
            steps {
                sshagent(credentials: ['ec2_ssh']) {
                    sh '''
                        set -eu
                        ssh -o StrictHostKeyChecking=no ec2-user@${APP_HOST} \
                            "APP_IMAGE='${IMAGE_NAME}:${IMAGE_TAG}' \
                             APP_VERSION='${IMAGE_TAG}' \
                             bash -s" < scripts/deploy.sh

                        sleep 15
                        ssh -o StrictHostKeyChecking=no ec2-user@${APP_HOST} \
                            "curl -fsS http://localhost/health"
                    '''
                }
            }
        }
    }

    post {
        always {
            // The lab's cleanup requirement.
            sh '''
                set +e
                docker logout
                docker rmi "${IMAGE_NAME}:${IMAGE_TAG}"
                docker image prune -f
                docker container prune -f
                rm -rf .venv
                exit 0
            '''
        }
    }
}