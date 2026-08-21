// The stripped-back version: the six stages the lab asks for, and little else.
// Compare against the full Jenkinsfile — the difference between the two files
// is the complete list of optional additions.

pipeline {
    agent any

    triggers {
        githubPush()
    }

    parameters {
        string(name: 'DOCKERHUB_USER', defaultValue: 'voidmaster', description: 'Your Docker Hub username (lowercase)')
        string(name: 'APP_HOST',       defaultValue: '10.20.1.14', description: 'terraform output -raw app_private_ip')
    }

    options {
        // A stuck build otherwise holds the only executor forever.
        timeout(time: 20, unit: 'MINUTES')
        disableConcurrentBuilds()
    }

    environment {
        IMAGE_TAG = "${env.BUILD_NUMBER}"
    }

    stages {

        stage('Checkout') {
            steps {
                checkout scm
                script {
                    // Fail here with a clear message rather than four stages
                    // later with "repository name must be lowercase".
                    if (!params.DOCKERHUB_USER?.trim()) {
                        error('DOCKERHUB_USER is empty. Use "Build with Parameters".')
                    }
                    if (!params.APP_HOST?.trim()) {
                        error('APP_HOST is empty. Run: terraform output -raw app_private_ip')
                    }
                    env.IMAGE_NAME = "${params.DOCKERHUB_USER.trim().toLowerCase()}/weather-app"
                    env.FULL_IMAGE = "${env.IMAGE_NAME}:${env.IMAGE_TAG}"
                }
            }
        }

        stage('Install / Build') {
            steps {
                sh '''
                    set -eu
                    python3 -m venv .venv
                    . .venv/bin/activate
                    pip install --upgrade pip
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
                sh 'docker build --build-arg APP_VERSION="${IMAGE_TAG}" -t "${FULL_IMAGE}" app/'
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
                        docker push "${FULL_IMAGE}"
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
                            "APP_IMAGE='${FULL_IMAGE}' \
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
            // The lab's cleanup requirement. set +e / exit 0 so cleanup
            // failures never fail the build.
            sh '''
                set +e
                docker logout
                docker rmi "${FULL_IMAGE}"
                docker image prune -f
                docker container prune -f
                rm -rf .venv
                exit 0
            '''
        }
    }
}